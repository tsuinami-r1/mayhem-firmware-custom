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

#include "ui.hpp"
#include "ui_widget.hpp"
#include "ui_navigation.hpp"
#include "ui_transmitter.hpp"

#include "telensa.hpp"
#include "message.hpp"
#include "transmitter_model.hpp"
#include "app_settings.hpp"
#include "radio_state.hpp"
#include "portapack.hpp"

namespace ui::external_app::telensa_tx {

class TelensaTXView : public View {
   public:
    TelensaTXView(NavigationView& nav);
    ~TelensaTXView();

    void focus() override;

    std::string title() const override { return "UNB FSK TX"; };

   private:
    TxRadioState radio_state_{
        920012500 /* frequency */,
        1750000 /* bandwidth */,
        UNB_BASEBAND_RATE /* sampling rate */
    };
    app_settings::SettingsManager settings_{
        "tx_unbfsk", app_settings::Mode::TX};

    enum tx_modes {
        IDLE = 0,
        SINGLE,
        CONTINUOUS
    };

    tx_modes tx_mode = IDLE;

    HopSequencer hopper{};

    void start_tx();
    void stop_tx();
    void on_tx_progress(const uint32_t progress, const bool done);

    /* Reads the payload SymField into a byte array. Returns byte count. */
    size_t read_payload(uint8_t* out);

    /* Retunes to the currently selected channel and refreshes the readout. */
    void update_frequency();

    /* Recomputes the frame-length / burst-duration readout. */
    void update_status();

    /* Advances the channel according to the selected hop mode. */
    void advance_hop();

    Labels labels{
        {{0 * 8, 1 * 8}, "UNB 2-FSK bench generator", Theme::getInstance()->fg_light->foreground},
        {{0 * 8, 3 * 8}, "Band:", Theme::getInstance()->fg_light->foreground},
        {{0 * 8, 5 * 8}, "Channel:", Theme::getInstance()->fg_light->foreground},
        {{0 * 8, 9 * 8}, "Deviation:", Theme::getInstance()->fg_light->foreground},
        {{18 * 8, 9 * 8}, "Hz", Theme::getInstance()->fg_light->foreground},
        {{0 * 8, 11 * 8}, "Sym rate:", Theme::getInstance()->fg_light->foreground},
        {{18 * 8, 11 * 8}, "bps", Theme::getInstance()->fg_light->foreground},
        {{0 * 8, 13 * 8}, "Preamble:", Theme::getInstance()->fg_light->foreground},
        {{16 * 8, 13 * 8}, "bytes 0x55", Theme::getInstance()->fg_light->foreground},
        {{0 * 8, 15 * 8}, "Sync:", Theme::getInstance()->fg_light->foreground},
        {{0 * 8, 17 * 8}, "Payload:", Theme::getInstance()->fg_light->foreground},
        {{0 * 8, 19 * 8}, "Hop:", Theme::getInstance()->fg_light->foreground},
        {{0 * 8, 21 * 8}, "Mode:", Theme::getInstance()->fg_light->foreground}};

    OptionsField field_band{
        {6 * 8, 3 * 8},
        11,
        {{"HK 920-925", BAND_HK},
         {"US 910-920", BAND_US},
         {"EU 869.4  ", BAND_EU}}};

    NumberField field_channel{
        {9 * 8, 5 * 8},
        3,
        {0, 380},
        1,
        ' '};

    Text text_frequency{
        {0 * 8, 7 * 8, 30 * 8, 8},
        ""};

    /* Deviation is unpublished; the range is deliberately wide so a measured
     * value can be dialled in without a rebuild. */
    NumberField field_deviation{
        {11 * 8, 9 * 8},
        5,
        {25, 25000},
        25,
        ' '};

    NumberField field_symrate{
        {11 * 8, 11 * 8},
        5,
        {50, 20000},
        50,
        ' '};

    NumberField field_preamble{
        {11 * 8, 13 * 8},
        2,
        {0, 32},
        1,
        ' '};

    SymField sym_sync{
        {11 * 8, 15 * 8},
        4,
        SymField::Type::Hex};

    SymField sym_payload{
        {9 * 8, 17 * 8},
        UNB_PAYLOAD_NIBBLES,
        SymField::Type::Hex};

    OptionsField field_hop{
        {6 * 8, 19 * 8},
        10,
        {{"Fixed     ", 0},
         {"Sequential", 1},
         {"Pseudo-rnd", 2}}};

    OptionsField field_mode{
        {6 * 8, 21 * 8},
        10,
        {{"Single    ", 0},
         {"Continuous", 1}}};

    Text text_status{
        {0 * 8, 23 * 8, 30 * 8, 8},
        ""};

    ProgressBar progressbar{
        {UI_POS_X(0), UI_POS_Y_BOTTOM(5), screen_width, 16},
    };

    TransmitterView tx_view{
        (int16_t)UI_POS_Y_BOTTOM(4),
        10000,
        12};

    MessageHandlerRegistration message_handler_tx_progress{
        Message::ID::TXProgress,
        [this](const Message* const p) {
            const auto message = *reinterpret_cast<const TXProgressMessage*>(p);
            this->on_tx_progress(message.progress, message.done);
        }};
};

}  // namespace ui::external_app::telensa_tx
