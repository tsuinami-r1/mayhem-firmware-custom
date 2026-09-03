/*
 * Copyright (C) 2016 Jared Boone, ShareBrained Technology, Inc.
 * Copyright (C) 2016 Furrtek
 * Copyright (C) 2020 Shao
 * Copyright (C) 2026 Claude / PortaPack contributors
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
 * Drone Geofence TX
 *
 * Creates a "no-fly zone" for GNSS-dependent drones by transmitting a
 * spoofed GPS L1 C/A constellation whose navigation solution places any
 * receiver inside a well-known restricted area (e.g. an airport).
 *
 * Widest-possible fleet coverage is achieved by targeting GPS L1 C/A
 * (1575.42 MHz): it is the one signal that virtually every compliant
 * consumer / commercial drone (DJI, Autel, Parrot, Skydio, Yuneec, ...)
 * tracks and uses for its onboard geofence / no-fly-zone enforcement.
 * A drone that believes it is standing inside a restricted zone will,
 * depending on how its firmware reacts, refuse to arm / take off or warn
 * the operator.
 *
 * The transmitted position is fully determined by the pre-generated C8
 * scenario file (built off-device with gps-sdr-sim). This app curates the
 * workflow around that: pick a zone, it loads the matching scenario file
 * from the GEOFENCE folder, locks the L1 carrier and transmits it in a
 * continuous loop.
 */

#ifndef __UI_DRONE_GEOFENCE_HPP__
#define __UI_DRONE_GEOFENCE_HPP__

#include "app_settings.hpp"
#include "ui_language.hpp"
#include "radio_state.hpp"
#include "ui_widget.hpp"
#include "ui_navigation.hpp"
#include "ui_receiver.hpp"
#include "ui_freq_field.hpp"
#include "replay_thread.hpp"
#include "ui_spectrum.hpp"
#include "ui_transmitter.hpp"

#include <string>
#include <memory>

namespace ui::external_app::drone_geofence {

// A curated no-fly-zone reference location. The coordinates are used to
// look up / label the scenario file and to show the operator the exact
// gps-sdr-sim command needed to generate it.
struct GeofenceZone {
    const char* name;  // Menu label.
    const char* code;  // Scenario file base name (<code>.C8).
    float lat;         // Degrees, north positive.
    float lon;         // Degrees, east positive.
};

class DroneGeofenceView : public View {
   public:
    DroneGeofenceView(NavigationView& nav);
    ~DroneGeofenceView();

    void on_hide() override;
    void set_parent_rect(const Rect new_parent_rect) override;
    void focus() override;

    std::string title() const override { return "Drone Geofence"; };

   private:
    NavigationView& nav_;
    TxRadioState radio_state_{
        1575420000 /* frequency (GPS L1 C/A) */,
        15000000 /* bandwidth */,
        2600000 /* sampling rate */
    };
    app_settings::SettingsManager settings_{
        "tx_geofence", app_settings::Mode::TX};

    static constexpr ui::Dim header_height = 6 * 16;

    const size_t read_size{16384};
    const size_t buffer_count{3};

    void on_file_changed(const std::filesystem::path& new_file_path);
    void on_tx_progress(const uint32_t progress);

    void on_zone_changed(size_t index);
    void on_band_changed(size_t index);
    void show_zone_help();

    void toggle();
    void start();
    void stop(const bool do_loop);
    bool is_active() const;
    void set_ready();
    void handle_replay_thread_done(const uint32_t return_code);
    void file_error();

    void set_file_loaded(bool loaded);

    size_t zone_index_{0};
    bool file_loaded_{false};

    std::filesystem::path file_path{};
    std::unique_ptr<ReplayThread> replay_thread{};
    bool ready_signal{false};

    Labels labels{
        {{0 * 8, 5 * 16}, "Band", Theme::getInstance()->fg_light->foreground}};

    OptionsField option_zone{
        {0 * 8, 0 * 16},
        26,
        {}};

    Button button_help{
        {27 * 8, 0 * 16, 3 * 8, 1 * 16},
        "?"};

    Text text_target{
        {0 * 8, 1 * 16, 30 * 8, 16},
        "-"};

    Button button_open{
        {0 * 8, 2 * 16, 10 * 8, 2 * 16},
        "Open file"};

    Text text_filename{
        {11 * 8, 2 * 16, 12 * 8, 16},
        "-"};
    Text text_sample_rate{
        {24 * 8, 2 * 16, 6 * 8, 16},
        "-"};

    Text text_duration{
        {11 * 8, 3 * 16, 6 * 8, 16},
        "-"};
    ProgressBar progressbar{
        {18 * 8, 3 * 16, 12 * 8, 16}};

    TxFrequencyField field_frequency{
        {0 * 8, 4 * 16},
        nav_};

    TransmitterView2 tx_view{
        {11 * 8, 4 * 16},
        /*short_ui*/ true};

    Checkbox check_loop{
        {21 * 8, 4 * 16},
        4,
        LanguageHelper::currentMessages[LANG_LOOP],
        true};
    ImageButton button_play{
        {screen_width - 2 * 8, 4 * 16, 2 * 8, 1 * 16},
        &bitmap_play,
        Theme::getInstance()->fg_green->foreground,
        Theme::getInstance()->fg_green->background};

    OptionsField option_band{
        {5 * 8, 5 * 16},
        11,
        {}};

    Text text_status{
        {17 * 8, 5 * 16, 13 * 8, 16},
        "no file"};

    spectrum::WaterfallView waterfall{};

    MessageHandlerRegistration message_handler_replay_thread_error{
        Message::ID::ReplayThreadDone,
        [this](const Message* const p) {
            const auto message = *reinterpret_cast<const ReplayThreadDoneMessage*>(p);
            this->handle_replay_thread_done(message.return_code);
        }};

    MessageHandlerRegistration message_handler_fifo_signal{
        Message::ID::RequestSignal,
        [this](const Message* const p) {
            const auto message = static_cast<const RequestSignalMessage*>(p);
            if (message->signal == RequestSignalMessage::Signal::FillRequest) {
                this->set_ready();
            }
        }};

    MessageHandlerRegistration message_handler_tx_progress{
        Message::ID::TXProgress,
        [this](const Message* const p) {
            const auto message = *reinterpret_cast<const TXProgressMessage*>(p);
            this->on_tx_progress(message.progress);
        }};
};

} /* namespace ui::external_app::drone_geofence */

#endif /*__UI_DRONE_GEOFENCE_HPP__*/
