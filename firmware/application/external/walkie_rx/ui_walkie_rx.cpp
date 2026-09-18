/*
 * Copyright (C) 2026 PortaPack Mayhem
 *
 * This file is part of PortaPack.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2, or (at your option)
 * any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; see the file COPYING.  If not, write to
 * the Free Software Foundation, Inc., 51 Franklin Street,
 * Boston, MA 02110-1301, USA.
 */

#include "ui_walkie_rx.hpp"

#include "audio.hpp"
#include "baseband_api.hpp"
#include "portapack.hpp"
#include "string_format.hpp"
#include "tone_key.hpp"
#include "ui_mictx.hpp"

using namespace portapack;

namespace ui::external_app::walkie_rx {

/* HackRF front-end defaults applied on the very first run only (afterwards
 * the user's saved gains are restored). Moderate gain, no RF amp: a handheld
 * a few metres away will otherwise overload the mixer. */
static constexpr uint8_t default_lna_db = 32;
static constexpr uint8_t default_vga_db = 24;

/* Mic TX "TXBW" (FM deviation, kHz) matching the preset's channel bandwidth.
 * Wide (25 kHz) radios deviate 5 kHz, narrow (12.5 kHz) ones 2.5 kHz; the
 * field is in whole kHz so narrow rounds up to 3. */
static uint32_t tx_deviation_khz_for(uint8_t bw) {
    return bw >= BW_WIDE ? 5 : 3;
}

static std::string tone_text(const WalkieChannel& ch) {
    if (ch.ctcss_x10)
        return "CTCSS " + to_string_dec_uint(ch.ctcss_x10 / 10) + "." + to_string_dec_uint(ch.ctcss_x10 % 10);
    if (ch.dcs)
        return "DCS " + to_string_dec_uint(ch.dcs & DCS_CODE_MASK, 3, '0') + ((ch.dcs & DCS_INV) ? "I" : "N");
    return "No tone";
}

/* Frequency as "462.5625MHz": as many decimals as needed, at least three. */
static std::string frequency_text(uint32_t hz) {
    std::string s = to_string_dec_uint(hz / 1'000'000) + ".";
    uint32_t frac = hz % 1'000'000;
    std::string digits = to_string_dec_uint(frac, 6, '0');
    size_t keep = 6;
    while (keep > 3 && digits[keep - 1] == '0')
        keep--;
    return s + digits.substr(0, keep) + "MHz";
}

WalkieRxView::WalkieRxView(NavigationView& nav)
    : nav_{nav} {
    // A baseband image must be running before the waterfall is added.
    baseband::run_image(portapack::spi_flash::image_tag_nfm_audio);

    add_children({
        &options_radio,
        &rssi,
        &channel_meter,
        &audio_meter,
        &field_volume,
        &options_channel,
        &text_frequency,
        &field_lna,
        &field_vga,
        &text_sq_label,
        &field_squelch,
        &text_preset,
        &text_rx_tone,
        &button_monitor,
        &button_ptt,
        &waterfall,
    });

    if (!settings_.loaded()) {
        receiver_model.set_lna(default_lna_db);
        receiver_model.set_vga(default_vga_db);
        receiver_model.set_rf_amp(false);
    }

    // Everything a walkie fixes: NFM, 3.072 MHz baseband, 1.75 MHz IF filter.
    receiver_model.set_modulation(ReceiverModel::Mode::NarrowbandFMAudio);
    receiver_model.set_sampling_rate(3072000);
    receiver_model.set_baseband_bandwidth(1750000);
    receiver_model.set_hidden_offset(0);
    receiver_model.set_frequency_step(12500);

    field_squelch.on_change = [this](int32_t v) {
        monitor_ = false;
        button_monitor.set_text("MON");
        receiver_model.set_squelch_level(v);
    };

    button_monitor.on_select = [this](Button&) {
        monitor_ = !monitor_;
        button_monitor.set_text(monitor_ ? "OPEN" : "MON");
        apply_squelch();
    };

    button_ptt.on_select = [this](Button&) {
        on_ptt();
    };

    options_radio.on_change = [this](size_t index, OptionsField::value_t) {
        apply_radio(index);
    };

    options_channel.on_change = [this](size_t index, OptionsField::value_t) {
        apply_channel(index);
    };

    // Restore the saved radio/slot. The option lists are filled with the
    // handlers detached (set_options would otherwise fire on_change(0) and
    // clobber the saved indices), then the preset is applied explicitly.
    populate_radios();
    if (radio_index_ >= walkie_radio_count)
        radio_index_ = 0;
    options_radio.set_selected_index(radio_index_, false);
    apply_radio(radio_index_);

    text_sq_label.set_style(Theme::getInstance()->fg_light);
    clear_rx_tone();

    audio::set_rate(audio::Rate::Hz_24000);
    audio::output::start();
    receiver_model.enable();
    audio::output::unmute();
}

WalkieRxView::~WalkieRxView() {
    audio::output::stop();
    receiver_model.disable();
    baseband::shutdown();
}

void WalkieRxView::set_parent_rect(Rect new_parent_rect) {
    View::set_parent_rect(new_parent_rect);
    waterfall.set_parent_rect({0, header_height, new_parent_rect.width(), new_parent_rect.height() - header_height});
}

void WalkieRxView::focus() {
    options_channel.focus();
}

const WalkieRadio& WalkieRxView::radio() const {
    return walkie_radios[radio_index_ < walkie_radio_count ? radio_index_ : 0];
}

const WalkieChannel& WalkieRxView::channel() const {
    const auto& r = radio();
    return r.channels[channel_index_ < r.channel_count ? channel_index_ : 0];
}

/* OptionsField::set_options selects index 0 and fires on_change; fill the
 * list with the handler detached so the caller decides what gets applied. */
static void set_options_silently(OptionsField& field, OptionsField::options_t options) {
    auto handler = std::move(field.on_change);
    field.on_change = nullptr;
    field.set_options(std::move(options));
    field.on_change = std::move(handler);
}

void WalkieRxView::populate_radios() {
    OptionsField::options_t options;
    options.reserve(walkie_radio_count);
    for (size_t i = 0; i < walkie_radio_count; i++)
        options.emplace_back(walkie_radios[i].name, (int32_t)i);
    set_options_silently(options_radio, std::move(options));
}

void WalkieRxView::populate_channels() {
    const auto& r = radio();
    OptionsField::options_t options;
    options.reserve(r.channel_count);
    for (size_t i = 0; i < r.channel_count; i++)
        options.emplace_back(std::string(r.channel_prefix) + " " + to_string_dec_uint(r.channels[i].number), (int32_t)i);
    set_options_silently(options_channel, std::move(options));
}

void WalkieRxView::apply_radio(size_t index) {
    if (index >= walkie_radio_count)
        index = 0;
    radio_index_ = index;

    // Keep the slot position when the new radio has it (FRS CH 5 on a
    // Motorola is FRS CH 5 on a Midland), otherwise start at the first slot.
    if (channel_index_ >= radio().channel_count)
        channel_index_ = 0;

    populate_channels();
    options_channel.set_selected_index(channel_index_, false);
    apply_channel(channel_index_);
}

void WalkieRxView::apply_channel(size_t index) {
    const auto& r = radio();
    if (index >= r.channel_count)
        index = 0;
    channel_index_ = index;
    const auto& ch = channel();

    // Factory settings of this slot: frequency, IF/audio bandwidth, squelch.
    receiver_model.set_target_frequency(ch.freq_hz);
    receiver_model.set_nbfm_configuration(ch.bw);
    monitor_ = false;
    button_monitor.set_text("MON");
    field_squelch.set_value(r.squelch, false);
    apply_squelch();

    text_frequency.set(frequency_text(ch.freq_hz));
    update_preset_text();
    clear_rx_tone();
}

void WalkieRxView::apply_squelch() {
    receiver_model.set_squelch_level(monitor_ ? 0 : field_squelch.value());
}

void WalkieRxView::update_preset_text() {
    const auto& ch = channel();
    std::string s = tone_text(ch);
    // Pad to 12 so the W/N marker stays in a fixed column.
    while (s.length() < 12)
        s += ' ';
    s += (ch.bw >= BW_WIDE) ? "W" : "N";
    text_preset.set(s);
}

void WalkieRxView::clear_rx_tone() {
    tone_stable_count_ = 0;
    tone_age_frames_ = tone_hold_frames;
    text_rx_tone.set_style(Theme::getInstance()->fg_light);
    text_rx_tone.set(channel().ctcss_x10 ? "RX --.-" : "RX");
}

/* The NFM baseband reports the currently decoded CTCSS tone (0.01 Hz units)
 * while a carrier is open. Show it, and colour it against the preset:
 * green = the tone this slot expects, red = some other tone, plain = the
 * preset has no tone to compare with. */
void WalkieRxView::on_coded_squelch(uint32_t value_centihz) {
    tone_age_frames_ = 0;

    // Same noise filter as Audio RX: a jump of >10 Hz between reports is
    // not a tone yet, wait for two consistent reports.
    const uint32_t delta = (value_centihz > last_tone_centihz_) ? value_centihz - last_tone_centihz_ : last_tone_centihz_ - value_centihz;
    last_tone_centihz_ = value_centihz;
    if (delta > 10 * 100) {
        tone_stable_count_ = 0;
        return;
    }
    if (tone_stable_count_ < 2) {
        tone_stable_count_++;
        if (tone_stable_count_ < 2)
            return;
    }

    const auto& ch = channel();
    const Style* style = Theme::getInstance()->fg_light;
    if (ch.ctcss_x10) {
        const uint32_t expected = ch.ctcss_x10 * 10;
        const uint32_t diff = (value_centihz > expected) ? value_centihz - expected : expected - value_centihz;
        style = (diff <= tone_match_tolerance_centihz) ? Theme::getInstance()->fg_green : Theme::getInstance()->fg_red;
    }
    text_rx_tone.set_style(style);
    text_rx_tone.set("RX " + tonekey::fx100_string(value_centihz));
}

void WalkieRxView::on_frame_sync() {
    if (tone_age_frames_ >= tone_hold_frames)
        return;
    if (++tone_age_frames_ >= tone_hold_frames)
        clear_rx_tone();
}

/* PTT: jump into Mic TX on this slot's frequency with this slot's CTCSS tone
 * and a deviation matching its bandwidth. Mic TX keeps its own RX section, so
 * the conversation continues from there. DCS is not a tone Mic TX can key, so
 * DCS slots hand over with no tone. */
void WalkieRxView::on_ptt() {
    const auto& ch = channel();

    auto settings = receiver_model.settings();
    settings.frequency_app_override = ch.freq_hz;
    settings.mode = ReceiverModel::Mode::NarrowbandFMAudio;

    int32_t tone_index = 0;
    if (ch.ctcss_x10) {
        const auto idx = tonekey::tone_key_index_by_value(ch.ctcss_x10 * 10);
        if (idx >= 0) {
            const uint32_t table_hz100 = tonekey::tone_keys[idx].second;
            const uint32_t want = ch.ctcss_x10 * 10;
            const uint32_t diff = (table_hz100 > want) ? table_hz100 - want : want - table_hz100;
            if (diff <= 50)
                tone_index = idx;
        }
    }

    nav_.replace<MicTXView>(settings, tone_index, tx_deviation_khz_for(ch.bw));
}

}  // namespace ui::external_app::walkie_rx
