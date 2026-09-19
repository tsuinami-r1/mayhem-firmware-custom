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

#include "ui_drone_geofence.hpp"
#include "string_format.hpp"

#include "ui_fileman.hpp"
#include "io_file.hpp"
#include "metadata_file.hpp"
#include "utility.hpp"
#include "file_path.hpp"

#include "baseband_api.hpp"
#include "portapack.hpp"
#include "portapack_persistent_memory.hpp"

using namespace portapack;
namespace fs = std::filesystem;

namespace ui::external_app::drone_geofence {

// GNSS bands, in enforcement priority order. The HackRF has one transmit
// chain, so these cannot be radiated at the same time: selecting several makes
// the app hop around them (see begin_cycle_entry / handle_replay_thread_done).
//
// L1 is first because it gives the widest fleet coverage: GPS L1 C/A, Galileo
// E1, BeiDou B1C and QZSS L1 all sit on 1575.42 MHz, so one transmission
// covers that whole stack at once. The other bands are 14 to 400 MHz away and
// each needs its own retune.
static constexpr GnssBand bands[] = {
    {"L1", 1575420000},    // GPS L1 C/A + Galileo E1 + BeiDou B1C + QZSS L1
    {"B1I", 1561098000},   // BeiDou B1I
    {"GLON", 1602000000},  // GLONASS L1 (FDMA centre)
    {"L5", 1176450000},    // GPS L5 + Galileo E5a + BeiDou B2a
    {"L2C", 1227600000},   // GPS L2C
};
static constexpr size_t band_count = sizeof(bands) / sizeof(bands[0]);

// band_checks_ is a fixed array of checkbox pointers; keep the two in step so
// adding a band without adding its checkbox can't walk off the end.
static_assert(band_count == 5, "band_checks_ must have one entry per band");

// Curated no-fly-zone reference locations. Index 0 is the manual entry
// (open any file). The rest map to <code>_<band>.C8 scenario files in the
// GEOFENCE folder and drive the gps-sdr-sim generation hint.
static constexpr GeofenceZone zones[] = {
    {"Custom / open file", "", 0.0f, 0.0f},
    {"LHR London Heathrow", "LHR", 51.4700f, -0.4543f},
    {"JFK New York", "JFK", 40.6413f, -73.7781f},
    {"LAX Los Angeles", "LAX", 33.9416f, -118.4085f},
    {"CDG Paris Ch.deGaulle", "CDG", 49.0097f, 2.5479f},
    {"FRA Frankfurt", "FRA", 50.0379f, 8.5622f},
    {"AMS Amsterdam", "AMS", 52.3105f, 4.7683f},
    {"DXB Dubai", "DXB", 25.2532f, 55.3657f},
    {"HKG Hong Kong", "HKG", 22.3080f, 113.9185f},
    {"HND Tokyo Haneda", "HND", 35.5494f, 139.7798f},
    {"SIN Singapore", "SIN", 1.3644f, 103.9915f},
    {"SYD Sydney", "SYD", -33.9399f, 151.1753f},
};
static constexpr size_t zone_count = sizeof(zones) / sizeof(zones[0]);

static bool file_exists(const fs::path& path) {
    File probe;
    return !probe.open(path);
}

static std::string format_coord(float value, char pos, char neg) {
    char hemi = (value >= 0.0f) ? pos : neg;
    float mag = (value >= 0.0f) ? value : -value;
    return to_string_decimal(mag, 4) + hemi;
}

// Signed decimal for the gps-sdr-sim command line. to_string_decimal() loses
// the sign when the integer part is negative zero (e.g. -0.4543), so build it
// from the magnitude and prepend the sign ourselves.
static std::string format_signed(float value) {
    float mag = (value >= 0.0f) ? value : -value;
    std::string s = to_string_decimal(mag, 4);
    return (value < 0.0f) ? ("-" + s) : s;
}

void DroneGeofenceView::set_ready() {
    ready_signal = true;
}

void DroneGeofenceView::set_file_loaded(bool loaded) {
    file_loaded_ = loaded;
    update_band_summary();
}

// Which scenario file backs a band for the current zone, or empty if none.
fs::path DroneGeofenceView::band_file_for(size_t band_index) const {
    if (zone_index_ == 0 || zone_index_ >= zone_count || band_index >= band_count)
        return {};

    const std::string code{zones[zone_index_].code};
    auto path = geofence_dir / (code + "_" + bands[band_index].label + ".C8");
    if (file_exists(path))
        return path;

    // Backwards compatibility: the original single-band layout stored the L1
    // scenario as <code>.C8, so keep honouring that for L1.
    if (band_index == 0) {
        auto legacy = geofence_dir / (code + ".C8");
        if (file_exists(legacy))
            return legacy;
    }

    return {};
}

// Load a scenario into the UI fields. Does not touch transmit state.
bool DroneGeofenceView::load_scenario(const fs::path& path) {
    File::Size file_size{};

    {
        File data_file;
        auto error = data_file.open(path);
        if (error)
            return false;

        file_size = data_file.size();
    }

    file_path = path;

    // Honour the file's own sample rate / centre frequency when it ships
    // metadata; band hopping overrides the frequency afterwards.
    auto metadata = read_metadata_file(get_metadata_path(file_path));
    if (metadata) {
        field_frequency.set_value(metadata->center_frequency);
        transmitter_model.set_sampling_rate(metadata->sample_rate);
    }

    text_sample_rate.set(unit_auto_scale(transmitter_model.sampling_rate(), 3, 1) + "Hz");
    progressbar.set_max(file_size);
    text_filename.set(truncate(file_path.filename().string(), 12));

    auto duration = ms_duration(file_size, transmitter_model.sampling_rate(), 2);
    text_duration.set(to_string_time_ms(duration));

    return true;
}

void DroneGeofenceView::on_file_changed(const fs::path& new_file_path) {
    // Loading a different scenario must not leave the previous one streaming.
    if (is_active() || cycling_)
        stop();

    if (!load_scenario(new_file_path)) {
        file_error();
        set_file_loaded(false);
        return;
    }

    set_file_loaded(true);

    // TODO: fix in UI framework with 'try_focus()'?
    // Hack around focus getting called by ctor before parent is set.
    if (parent())
        button_play.focus();
}

void DroneGeofenceView::on_zone_changed(size_t index) {
    if (index >= zone_count)
        return;

    // Switching the target zone changes the scenario files, so stop any
    // enforcement that is currently transmitting the previous ones.
    if (is_active() || cycling_)
        stop();

    zone_index_ = index;
    const auto& zone = zones[index];

    if (index == 0) {
        text_target.set("Custom: open a C8 GNSS scenario");
        set_file_loaded(false);
        return;
    }

    std::string coords = format_coord(zone.lat, 'N', 'S') + " " +
                         format_coord(zone.lon, 'E', 'W');
    text_target.set(std::string{zone.code} + " " + coords);

    ensure_directory(geofence_dir);

    // Preview the first selected band that actually has a scenario file, so the
    // filename / duration fields show something useful before transmitting.
    file_loaded_ = false;
    for (size_t i = 0; i < band_count; i++) {
        if (!band_checks_[i]->value())
            continue;
        auto path = band_file_for(i);
        if (path.empty())
            continue;
        if (load_scenario(path)) {
            field_frequency.set_value(bands[i].freq);
            file_loaded_ = true;
        }
        break;
    }

    update_band_summary();
}

void DroneGeofenceView::on_bands_changed() {
    // Re-selecting bands mid-transmission would desync the cycle.
    if (is_active() || cycling_)
        stop();

    // In custom mode the manually opened file is the whole cycle, so band
    // selection is irrelevant and must not clear what the user just loaded.
    if (zone_index_ == 0) {
        update_band_summary();
        return;
    }

    on_zone_changed(zone_index_);
}

void DroneGeofenceView::show_zone_help() {
    const auto& zone = zones[zone_index_];

    if (zone_index_ == 0) {
        nav_.display_modal(
            "Geofence",
            "Load a GNSS scenario (.C8,\n"
            "sc8) built with gps-sdr-sim\n"
            "at a no-fly-zone coordinate.\n"
            "Pick a zone for band hopping.");
        return;
    }

    std::string lat = format_signed(zone.lat);
    std::string lon = format_signed(zone.lon);

    // Show the exact command to generate the missing scenario file. gps-sdr-sim
    // only covers L1; the other bands need their own generator.
    nav_.display_modal(
        std::string{zone.code} + " scenario",
        "Per band, as GEOFENCE/\n" +
            std::string{zone.code} +
            "_<BAND>.C8\n(L1 B1I GLON L5 L2C)\n\n"
            "L1 via gps-sdr-sim:\n"
            "gps-sdr-sim -e brdc \\\n -l " +
            lat + "," + lon +
            ",100 \\\n -s 2600000 -b 8 \\\n -o " +
            std::string{zone.code} + "_L1.C8");
}

void DroneGeofenceView::on_tx_progress(const uint32_t progress) {
    progressbar.set_value(progress);
}

void DroneGeofenceView::focus() {
    option_zone.focus();
}

void DroneGeofenceView::file_error() {
    nav_.display_modal("Error", "File read error.");
}

bool DroneGeofenceView::is_active() const {
    return (bool)replay_thread;
}

void DroneGeofenceView::toggle() {
    if (is_active() || cycling_) {
        stop();
    } else {
        start();
    }
}

// Build the hop list: every selected band that has a scenario file for the
// current zone. Custom mode contributes one entry at the manual frequency.
size_t DroneGeofenceView::rebuild_cycle() {
    cycle_len_ = 0;

    if (zone_index_ == 0) {
        if (file_loaded_ && !file_path.empty()) {
            cycle_[0] = {file_path, field_frequency.value(), "CUSTOM"};
            cycle_len_ = 1;
        }
        return cycle_len_;
    }

    for (size_t i = 0; i < band_count && cycle_len_ < max_cycle; i++) {
        if (!band_checks_[i]->value())
            continue;
        auto path = band_file_for(i);
        if (path.empty())
            continue;
        cycle_[cycle_len_++] = {path, bands[i].freq, bands[i].label};
    }

    return cycle_len_;
}

void DroneGeofenceView::begin_cycle_entry(size_t pos) {
    if (pos >= cycle_len_)
        return;

    const auto& entry = cycle_[pos];

    if (!load_scenario(entry.path)) {
        stop();
        file_error();
        return;
    }

    // The band table is authoritative over any metadata in the file, so a
    // mislabelled scenario cannot send us to the wrong band mid-hop.
    field_frequency.set_value(entry.freq);

    start_stream();
}

void DroneGeofenceView::start_stream() {
    auto p = std::make_unique<FileReader>();
    auto open_error = p->open(file_path);
    if (open_error.is_valid()) {
        stop();
        file_error();
        return;
    }

    std::unique_ptr<stream::Reader> reader = std::move(p);

    replay_thread = std::make_unique<ReplayThread>(
        std::move(reader),
        read_size, buffer_count,
        &ready_signal,
        [](uint32_t return_code) {
            ReplayThreadDoneMessage message{return_code};
            EventDispatcher::send_message(message);
        });

    transmitter_model.enable();
    update_band_summary();
}

void DroneGeofenceView::stop_stream() {
    if (replay_thread)
        replay_thread.reset();

    transmitter_model.disable();
    ready_signal = false;
}

void DroneGeofenceView::start() {
    stop_stream();

    if (rebuild_cycle() == 0) {
        update_band_summary();
        return;
    }

    cycle_pos_ = 0;
    loops_done_ = 0;
    cycling_ = true;

    button_play.set_bitmap(&bitmap_stop);
    begin_cycle_entry(cycle_pos_);
}

void DroneGeofenceView::stop() {
    cycling_ = false;
    stop_stream();

    button_play.set_bitmap(&bitmap_play);
    progressbar.set_value(0);
    update_band_summary();
}

void DroneGeofenceView::handle_replay_thread_done(const uint32_t return_code) {
    if (return_code == ReplayThread::READ_ERROR) {
        stop();
        file_error();
        return;
    }

    if (return_code != ReplayThread::END_OF_FILE)
        return;

    if (!cycling_) {
        stop();
        return;
    }

    progressbar.set_value(0);

    // Dwell on this band for the configured number of scenario repeats, then
    // hop to the next selected band, wrapping at the end of the cycle.
    if (++loops_done_ < (uint32_t)field_repeat.value()) {
        stop_stream();
        begin_cycle_entry(cycle_pos_);
        return;
    }

    loops_done_ = 0;

    if (++cycle_pos_ >= cycle_len_) {
        cycle_pos_ = 0;
        if (!check_loop.value()) {
            stop();
            return;
        }
    }

    stop_stream();
    begin_cycle_entry(cycle_pos_);
}

void DroneGeofenceView::update_band_summary() {
    if (cycling_ && cycle_len_ > 0) {
        text_status.set("TX " + std::string{cycle_[cycle_pos_].label} + " " +
                        to_string_dec_uint(cycle_pos_ + 1) + "/" +
                        to_string_dec_uint(cycle_len_));
        button_play.set_focusable(true);
        return;
    }

    if (zone_index_ == 0) {
        text_status.set(file_loaded_ ? "armed: custom" : "no file");
        button_play.set_focusable(file_loaded_);
        return;
    }

    std::string ready;
    for (size_t i = 0; i < band_count; i++) {
        if (!band_checks_[i]->value())
            continue;
        if (band_file_for(i).empty())
            continue;
        if (!ready.empty())
            ready += ",";
        ready += bands[i].label;
    }

    text_status.set(ready.empty() ? "no scenario file" : ("armed: " + ready));
    button_play.set_focusable(!ready.empty());
}

DroneGeofenceView::DroneGeofenceView(
    NavigationView& nav)
    : nav_(nav) {
    baseband::run_prepared_image(portapack::memory::map::m4_code.base());

    add_children({
        &labels,
        &option_zone,
        &button_help,
        &text_target,
        &button_open,
        &text_filename,
        &text_sample_rate,
        &text_duration,
        &progressbar,
        &field_frequency,
        &tx_view,  // now it handles previous rfgain, rfamp.
        &check_loop,
        &button_play,
        &check_band_0,
        &check_band_1,
        &check_band_2,
        &check_band_3,
        &check_band_4,
        &button_all,
        &field_repeat,
        &text_status,
        &waterfall,
    });

    band_checks_[0] = &check_band_0;
    band_checks_[1] = &check_band_1;
    band_checks_[2] = &check_band_2;
    band_checks_[3] = &check_band_3;
    band_checks_[4] = &check_band_4;

    // L1 on by default: widest coverage, and matches single-band behaviour.
    check_band_0.set_value(true);
    for (size_t i = 0; i < band_count; i++) {
        band_checks_[i]->on_select = [this](Checkbox&, bool) {
            this->on_bands_changed();
        };
    }

    // Continuous enforcement is the point of a geofence, so cycle by default.
    check_loop.set_value(true);
    field_repeat.set_value(1);

    // Populate zone selector.
    OptionsField::options_t zone_options;
    for (size_t i = 0; i < zone_count; i++)
        zone_options.emplace_back(zones[i].name, (OptionsField::value_t)i);
    option_zone.set_options(zone_options);
    option_zone.on_change = [this](size_t index, OptionsField::value_t) {
        this->on_zone_changed(index);
    };

    field_frequency.set_step(5000);
    field_frequency.set_value(bands[0].freq);

    button_play.on_select = [this](ImageButton&) {
        this->toggle();
    };

    button_help.on_select = [this](Button&) {
        this->show_zone_help();
    };

    button_all.on_select = [this](Button&) {
        // Toggle between "every band" and "L1 only".
        bool all_on = true;
        for (size_t i = 0; i < band_count; i++)
            all_on = all_on && band_checks_[i]->value();

        for (size_t i = 0; i < band_count; i++)
            band_checks_[i]->set_value(all_on ? (i == 0) : true);

        this->on_bands_changed();
    };

    button_open.on_select = [this, &nav](Button&) {
        auto open_view = nav.push<FileLoadView>(".C8");
        ensure_directory(geofence_dir);
        open_view->push_dir(geofence_dir);
        open_view->on_changed = [this](std::filesystem::path new_file_path) {
            option_zone.set_selected_index(0, false);
            zone_index_ = 0;
            text_target.set("Custom: " + truncate(new_file_path.filename().string(), 18));
            on_file_changed(new_file_path);
        };
    };

    on_zone_changed(0);
}

DroneGeofenceView::~DroneGeofenceView() {
    transmitter_model.disable();
    baseband::shutdown();
}

void DroneGeofenceView::on_hide() {
    // TODO: Terrible kludge because widget system doesn't notify Waterfall that
    // it's being shown or hidden.
    if (is_active() || cycling_)
        stop();
    waterfall.on_hide();
    View::on_hide();
}

void DroneGeofenceView::set_parent_rect(const Rect new_parent_rect) {
    View::set_parent_rect(new_parent_rect);

    const ui::Rect waterfall_rect{0, header_height, new_parent_rect.width(), new_parent_rect.height() - header_height};
    waterfall.set_parent_rect(waterfall_rect);
}

} /* namespace ui::external_app::drone_geofence */
