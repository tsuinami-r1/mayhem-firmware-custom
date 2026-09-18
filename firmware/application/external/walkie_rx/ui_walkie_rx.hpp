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

/*
 * Walkie-Talkie: the Audio RX app with a walkie pre-baked in.
 *
 * The receiver is locked to narrowband FM and every knob that a handheld
 * fixes at the factory (frequency, channel bandwidth, tone squelch, squelch
 * level) is taken from a preset table. Pick the radio, pick the channel slot,
 * and the HackRF behaves like a factory-fresh unit of that model on that
 * channel. PTT hands the same frequency, tone and deviation to Mic TX.
 */

#ifndef __UI_WALKIE_RX_H__
#define __UI_WALKIE_RX_H__

#include "ui.hpp"
#include "ui_navigation.hpp"
#include "ui_receiver.hpp"
#include "ui_rssi.hpp"
#include "ui_channel.hpp"
#include "ui_audio.hpp"
#include "ui_spectrum.hpp"
#include "app_settings.hpp"
#include "radio_state.hpp"
#include "receiver_model.hpp"
#include "message.hpp"

#include "walkie_presets.hpp"

namespace ui::external_app::walkie_rx {

class WalkieRxView : public View {
   public:
    WalkieRxView(NavigationView& nav);
    ~WalkieRxView();

    WalkieRxView(const WalkieRxView&) = delete;
    WalkieRxView(WalkieRxView&&) = delete;
    WalkieRxView& operator=(const WalkieRxView&) = delete;
    WalkieRxView& operator=(WalkieRxView&&) = delete;

    void set_parent_rect(Rect new_parent_rect) override;
    void focus() override;

    std::string title() const override { return "Walkie-Talkie"; };

   private:
    static constexpr Dim header_height = 3 * 16;

    /* A decoded CTCSS tone counts as the preset's tone when it is within this
     * distance (0.01 Hz units). Adjacent standard tones are >= 2.3 Hz apart. */
    static constexpr uint32_t tone_match_tolerance_centihz = 100;

    /* Frames (60 Hz) without a tone report before the RX tone readout clears. */
    static constexpr uint32_t tone_hold_frames = 45;

    NavigationView& nav_;
    RxRadioState radio_state_{};

    // Persisted selection.
    uint32_t radio_index_{0};
    uint32_t channel_index_{0};

    app_settings::SettingsManager settings_{
        "rx_walkie",
        app_settings::Mode::RX,
        {
            {"radio"sv, &radio_index_},
            {"channel"sv, &channel_index_},
        }};

    bool monitor_{false};
    uint32_t last_tone_centihz_{0};
    uint8_t tone_stable_count_{0};
    uint32_t tone_age_frames_{tone_hold_frames};

    const WalkieRadio& radio() const;
    const WalkieChannel& channel() const;

    void populate_radios();
    void populate_channels();
    void apply_radio(size_t index);
    void apply_channel(size_t index);
    void apply_squelch();
    void update_preset_text();
    void clear_rx_tone();
    void on_coded_squelch(uint32_t value_centihz);
    void on_frame_sync();
    void on_ptt();

    // Row 0: radio selector + meters + volume.
    OptionsField options_radio{
        {UI_POS_X(0), UI_POS_Y(0)},
        17,
        {}};

    RSSI rssi{
        {UI_POS_X(21), 0, UI_POS_WIDTH_REMAINING(21) - UI_POS_WIDTH(2), 4}};

    Channel channel_meter{
        {UI_POS_X(21), 5, UI_POS_WIDTH_REMAINING(21) - UI_POS_WIDTH(2), 4}};

    Audio audio_meter{
        {UI_POS_X(21), 10, UI_POS_WIDTH_REMAINING(21) - UI_POS_WIDTH(2), 4}};

    AudioVolumeField field_volume{
        {screen_width - 2 * 8, UI_POS_Y(0)}};

    // Row 1: channel slot, frequency readout, gains, squelch.
    OptionsField options_channel{
        {UI_POS_X(0), UI_POS_Y(1)},
        6,
        {}};

    Text text_frequency{
        {UI_POS_X(7), UI_POS_Y(1), UI_POS_WIDTH(12), UI_POS_HEIGHT(1)},
        ""};

    LNAGainField field_lna{
        {UI_POS_X(20), UI_POS_Y(1)}};

    VGAGainField field_vga{
        {UI_POS_X(23), UI_POS_Y(1)}};

    Text text_sq_label{
        {UI_POS_X(25), UI_POS_Y(1), UI_POS_WIDTH(2), UI_POS_HEIGHT(1)},
        "SQ"};

    NumberField field_squelch{
        {UI_POS_X(27), UI_POS_Y(1)},
        2,
        {0, 99},
        1,
        ' '};

    // Row 2: preset tone/bandwidth, decoded RX tone, MON and PTT.
    Text text_preset{
        {UI_POS_X(0), UI_POS_Y(2), UI_POS_WIDTH(14), UI_POS_HEIGHT(1)},
        ""};

    Text text_rx_tone{
        {UI_POS_X(14), UI_POS_Y(2), UI_POS_WIDTH(8), UI_POS_HEIGHT(1)},
        ""};

    Button button_monitor{
        {UI_POS_X(22), UI_POS_Y(2), UI_POS_WIDTH(4), UI_POS_HEIGHT(1)},
        "MON"};

    Button button_ptt{
        {UI_POS_X(26), UI_POS_Y(2), UI_POS_WIDTH(4), UI_POS_HEIGHT(1)},
        "PTT"};

    spectrum::WaterfallView waterfall{false};

    MessageHandlerRegistration message_handler_coded_squelch{
        Message::ID::CodedSquelch,
        [this](const Message* p) {
            const auto message = *reinterpret_cast<const CodedSquelchMessage*>(p);
            this->on_coded_squelch(message.value);
        }};

    MessageHandlerRegistration message_handler_frame_sync{
        Message::ID::DisplayFrameSync,
        [this](const Message* const) {
            this->on_frame_sync();
        }};
};

}  // namespace ui::external_app::walkie_rx

#endif /* __UI_WALKIE_RX_H__ */
