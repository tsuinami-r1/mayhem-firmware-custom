/*
 * Copyright (C) 2026 Mayhem firmware contributors
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

#include "ui_telensa_tx.hpp"
#include "string_format.hpp"

#include "baseband_api.hpp"
#include "portapack_persistent_memory.hpp"

using namespace portapack;

namespace ui::external_app::telensa_tx {

void TelensaTXView::focus() {
    tx_view.focus();
}

size_t TelensaTXView::read_payload(uint8_t* out) {
    for (size_t c = 0; c < UNB_MAX_PAYLOAD_BYTES; c++) {
        uint8_t hi = sym_payload.get_offset(c * 2) & 0x0F;
        uint8_t lo = sym_payload.get_offset(c * 2 + 1) & 0x0F;
        out[c] = (hi << 4) | lo;
    }

    return UNB_MAX_PAYLOAD_BYTES;
}

void TelensaTXView::update_frequency() {
    const auto band = (band_plan_t)field_band.selected_index_value();
    const auto freq = channel_frequency(band, field_channel.value());

    transmitter_model.set_target_frequency(freq);

    // Printed as MHz to four decimals: the 25 kHz raster needs that resolution
    // to distinguish adjacent channels.
    text_frequency.set("  " + to_string_dec_uint(freq / 1000000) + "." +
                       to_string_dec_uint(static_cast<uint32_t>((freq % 1000000) / 100), 4, '0') +
                       " MHz");
}

void TelensaTXView::update_status() {
    const uint32_t frame_bits = (field_preamble.value() + 2 + UNB_MAX_PAYLOAD_BYTES) * 8;
    const uint32_t total_bits = frame_bits + UNB_PROC_FSK_TAIL_BITS;
    const uint32_t burst_ms = (total_bits * 1000) / field_symrate.value();

    text_status.set(to_string_dec_uint(total_bits) + " bits, " +
                    to_string_dec_uint(burst_ms) + " ms burst");
}

void TelensaTXView::advance_hop() {
    const auto band = (band_plan_t)field_band.selected_index_value();
    const auto count = static_cast<int32_t>(band_defs[band].channel_count);

    switch (field_hop.selected_index_value()) {
        case 1:  // Sequential
            field_channel.set_value((field_channel.value() + 1) % count);
            break;

        case 2:  // Pseudo-random
            field_channel.set_value(static_cast<int32_t>(hopper.next(count)));
            break;

        default:  // Fixed
            break;
    }
}

void TelensaTXView::start_tx() {
    uint8_t payload[UNB_MAX_PAYLOAD_BYTES];

    const auto payload_len = read_payload(payload);

    const auto frame_bits = build_frame(
        field_preamble.value(),
        sym_sync.to_integer() & 0xFFFF,
        payload,
        payload_len);

    /* proc_fsk transmits 32 bits past the stream length, so the bar has to
     * account for them or it will never reach the end. */
    progressbar.set_max(static_cast<uint32_t>(frame_bits + UNB_PROC_FSK_TAIL_BITS) / 8);

    transmitter_model.enable();

    baseband::set_fsk_data(
        static_cast<uint32_t>(frame_bits),
        UNB_BASEBAND_RATE / static_cast<uint32_t>(field_symrate.value()),
        static_cast<uint32_t>(field_deviation.value()),
        7 /* one progress tick per 8 bits */);
}

void TelensaTXView::stop_tx() {
    transmitter_model.disable();
    tx_mode = IDLE;
    tx_view.set_transmitting(false);
    progressbar.set_value(0);
}

void TelensaTXView::on_tx_progress(const uint32_t progress, const bool done) {
    if (!done) {
        progressbar.set_value(progress);
        return;
    }

    if (tx_mode == CONTINUOUS) {
        /* Hop and re-fire immediately. Bursts run back to back rather than on
         * a timed cadence - this is a calibration source, and unbroken output
         * is easier to find on an analyser. Deliberately no sleep here: this
         * runs on the message-handler thread and blocking it would freeze the
         * UI (see the flashing path in bht_tx for what that looks like). */
        advance_hop();
        update_frequency();
        start_tx();
    } else {
        stop_tx();
    }
}

TelensaTXView::~TelensaTXView() {
    transmitter_model.disable();
    baseband::shutdown();
}

TelensaTXView::TelensaTXView(NavigationView& nav) {
    baseband::run_image(portapack::spi_flash::image_tag_fsktx);

    add_children({&labels,
                  &field_band,
                  &field_channel,
                  &text_frequency,
                  &field_deviation,
                  &field_symrate,
                  &field_preamble,
                  &sym_sync,
                  &sym_payload,
                  &field_hop,
                  &field_mode,
                  &text_status,
                  &progressbar,
                  &tx_view});

    field_deviation.set_value(UNB_DEFAULT_DEVIATION);
    field_symrate.set_value(UNB_DEFAULT_SYMBOL_RATE);
    field_preamble.set_value(8);
    sym_sync.set_value(0x2DD4);
    sym_payload.set_value(0x0123456789ABCDEFULL);

    field_band.on_change = [this](size_t, OptionsField::value_t v) {
        const auto count = band_defs[(band_plan_t)v].channel_count;

        field_channel.set_range(0, count - 1);
        if ((uint32_t)field_channel.value() >= count)
            field_channel.set_value(count - 1);

        update_frequency();
    };

    field_channel.on_change = [this](int32_t) { update_frequency(); };
    field_preamble.on_change = [this](int32_t) { update_status(); };
    field_symrate.on_change = [this](int32_t) { update_status(); };

    // NB: set after the handlers so the initial selection refreshes the readouts.
    field_band.set_selected_index(BAND_HK);
    field_hop.set_selected_index(0);
    field_mode.set_selected_index(0);

    update_frequency();
    update_status();

    tx_view.on_edit_frequency = [this, &nav]() {
        auto new_view = nav.push<FrequencyKeypadView>(transmitter_model.target_frequency());
        new_view->on_changed = [this](rf::Frequency f) {
            transmitter_model.set_target_frequency(f);
            text_frequency.set("  manual tune");
        };
    };

    tx_view.on_start = [this]() {
        if (tx_mode == IDLE) {
            tx_mode = field_mode.selected_index_value() ? CONTINUOUS : SINGLE;
            hopper.reset();
            progressbar.set_value(0);
            tx_view.set_transmitting(true);
            start_tx();
        }
    };

    tx_view.on_stop = [this]() {
        stop_tx();
    };
}

}  // namespace ui::external_app::telensa_tx
