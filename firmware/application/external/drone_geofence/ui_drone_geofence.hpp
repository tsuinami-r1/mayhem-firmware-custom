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
    const char* code;  // Scenario file base name (<code>_<band>.C8).
    float lat;         // Degrees, north positive.
    float lon;         // Degrees, east positive.
};

// A GNSS band the app can enforce on. The HackRF has a single transmit chain,
// so bands cannot be radiated simultaneously - the app time-multiplexes
// ("hops") around the selected ones instead. `label` doubles as the scenario
// file suffix: <zone code>_<label>.C8.
struct GnssBand {
    const char* label;
    rf::Frequency freq;
};

// One step of the transmit cycle: a scenario file at a centre frequency.
struct CycleEntry {
    std::filesystem::path path;
    rf::Frequency freq;
    const char* label;
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

    static constexpr ui::Dim header_height = 7 * 16;

    static constexpr size_t max_cycle = 8;

    const size_t read_size{16384};
    const size_t buffer_count{3};

    void on_file_changed(const std::filesystem::path& new_file_path);
    bool load_scenario(const std::filesystem::path& path);
    void on_tx_progress(const uint32_t progress);

    void on_zone_changed(size_t index);
    void on_bands_changed();
    void show_zone_help();

    void toggle();
    void start();
    void stop();
    bool is_active() const;
    void set_ready();
    void handle_replay_thread_done(const uint32_t return_code);
    void file_error();

    void set_file_loaded(bool loaded);

    // Band-hopping engine.
    std::filesystem::path band_file_for(size_t band_index) const;
    size_t rebuild_cycle();
    void begin_cycle_entry(size_t pos);
    void start_stream();
    void stop_stream();
    void update_band_summary();

    size_t zone_index_{0};
    bool file_loaded_{false};

    CycleEntry cycle_[max_cycle]{};
    size_t cycle_len_{0};
    size_t cycle_pos_{0};
    uint32_t loops_done_{0};
    bool cycling_{false};

    // Band checkboxes addressed by index. A method rather than an array of
    // pointers so the class keeps no raw pointer members (-Weffc++).
    Checkbox& band_check(size_t index);

    std::filesystem::path file_path{};
    std::unique_ptr<ReplayThread> replay_thread{};
    bool ready_signal{false};

    Labels labels{
        {{0 * 8, 6 * 16}, "Rep", Theme::getInstance()->fg_light->foreground}};

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

    // Band multi-select. The HackRF radiates one band at a time, so ticking
    // several makes the app hop around them; ticking one behaves like a
    // single-band transmitter. Small checkboxes so the row is 16px tall.
    Checkbox check_band_0{{0, 5 * 16}, 2, "L1", true};
    Checkbox check_band_1{{34, 5 * 16}, 3, "B1I", true};
    Checkbox check_band_2{{76, 5 * 16}, 4, "GLON", true};
    Checkbox check_band_3{{126, 5 * 16}, 2, "L5", true};
    Checkbox check_band_4{{160, 5 * 16}, 3, "L2C", true};

    Button button_all{
        {25 * 8, 5 * 16, 5 * 8, 1 * 16},
        "All"};

    // Scenario repeats per band before hopping to the next one.
    NumberField field_repeat{
        {4 * 8, 6 * 16},
        1,
        {1, 9},
        1,
        ' '};

    Text text_status{
        {7 * 8, 6 * 16, 23 * 8, 16},
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
