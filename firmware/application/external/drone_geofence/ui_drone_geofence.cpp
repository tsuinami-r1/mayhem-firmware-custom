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

// GNSS L1 bands. GPS L1 C/A is first: it gives the widest fleet coverage
// because essentially every compliant drone tracks it for positioning /
// no-fly-zone enforcement. The other bands are provided for operators who
// generate matching scenarios with other tools; the transmitted content is
// always the loaded C8 file, this selector only moves the carrier.
static constexpr rf::Frequency freq_gps_l1 = 1575420000;
static constexpr rf::Frequency freq_glonass_l1 = 1602000000;
static constexpr rf::Frequency freq_beidou_b1i = 1561098000;

// Curated no-fly-zone reference locations. Index 0 is the manual entry
// (open any file). The rest map to <code>.C8 scenario files in the GEOFENCE
// folder and drive the gps-sdr-sim generation hint.
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
    button_play.set_focusable(loaded);
    text_status.set(loaded ? "armed:ready" : "no file");
}

void DroneGeofenceView::on_file_changed(const fs::path& new_file_path) {
    // Loading a different scenario must not leave the previous one streaming.
    if (is_active())
        stop(false);

    file_path = new_file_path;
    File::Size file_size{};

    {  // Get the size of the data file.
        File data_file;
        auto error = data_file.open(file_path);
        if (error) {
            file_error();
            set_file_loaded(false);
            return;
        }

        file_size = data_file.size();
    }

    // Get original record frequency if available.
    auto metadata_path = get_metadata_path(file_path);
    auto metadata = read_metadata_file(metadata_path);

    if (metadata) {
        field_frequency.set_value(metadata->center_frequency);
        transmitter_model.set_sampling_rate(metadata->sample_rate);
    }

    // UI Fixup.
    text_sample_rate.set(unit_auto_scale(transmitter_model.sampling_rate(), 3, 1) + "Hz");
    progressbar.set_max(file_size);
    text_filename.set(truncate(file_path.filename().string(), 12));

    auto duration = ms_duration(file_size, transmitter_model.sampling_rate(), 2);
    text_duration.set(to_string_time_ms(duration));

    set_file_loaded(true);

    // TODO: fix in UI framework with 'try_focus()'?
    // Hack around focus getting called by ctor before parent is set.
    if (parent())
        button_play.focus();
}

void DroneGeofenceView::on_zone_changed(size_t index) {
    if (index >= zone_count)
        return;

    // Switching the target zone changes the scenario file, so stop any
    // enforcement that is currently transmitting the previous one.
    if (is_active())
        stop(false);

    zone_index_ = index;
    const auto& zone = zones[index];

    if (index == 0) {
        text_target.set("Custom: open a C8 GPS scenario");
        return;
    }

    // Show the target no-fly-zone coordinates.
    std::string coords = format_coord(zone.lat, 'N', 'S') + " " +
                         format_coord(zone.lon, 'E', 'W');
    text_target.set(std::string{zone.code} + " " + coords);

    // Try to auto-load the matching scenario file from the GEOFENCE folder.
    ensure_directory(geofence_dir);
    auto candidate = geofence_dir / (std::string{zone.code} + ".C8");
    File probe;
    auto error = probe.open(candidate);
    if (error) {
        set_file_loaded(false);
        text_status.set("gen file (?)");
    } else {
        on_file_changed(candidate);
    }
}

void DroneGeofenceView::show_zone_help() {
    const auto& zone = zones[zone_index_];

    if (zone_index_ == 0) {
        nav_.display_modal(
            "Geofence",
            "Load a GPS L1 C/A scenario\n"
            "(.C8, 2.6 Msps, sc8) built\n"
            "with gps-sdr-sim, placed at\n"
            "a no-fly-zone coordinate.");
        return;
    }

    std::string lat = format_signed(zone.lat);
    std::string lon = format_signed(zone.lon);

    // Show the exact command to generate the missing scenario file.
    nav_.display_modal(
        std::string{zone.code} + " scenario",
        "Generate off-device, copy to\n"
        "GEOFENCE/" +
            std::string{zone.code} + ".C8:\n\n"
                                     "gps-sdr-sim -e brdc \\\n -l " +
            lat + "," + lon +
            ",100 \\\n -s 2600000 -b 8 \\\n -o " +
            std::string{zone.code} + ".C8");
}

void DroneGeofenceView::on_band_changed(size_t index) {
    switch (index) {
        case 1:
            field_frequency.set_value(freq_glonass_l1);
            break;
        case 2:
            field_frequency.set_value(freq_beidou_b1i);
            break;
        case 0:
        default:
            field_frequency.set_value(freq_gps_l1);
            break;
    }
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
    if (is_active()) {
        stop(false);
    } else {
        start();
    }
}

void DroneGeofenceView::start() {
    if (!file_loaded_) {
        text_status.set("no file");
        return;
    }

    stop(false);

    std::unique_ptr<stream::Reader> reader;

    auto p = std::make_unique<FileReader>();
    auto open_error = p->open(file_path);
    if (open_error.is_valid()) {
        file_error();
    } else {
        reader = std::move(p);
    }

    if (reader) {
        button_play.set_bitmap(&bitmap_stop);
        text_status.set("ENFORCING");

        replay_thread = std::make_unique<ReplayThread>(
            std::move(reader),
            read_size, buffer_count,
            &ready_signal,
            [](uint32_t return_code) {
                ReplayThreadDoneMessage message{return_code};
                EventDispatcher::send_message(message);
            });
    }

    transmitter_model.enable();
}

void DroneGeofenceView::stop(const bool do_loop) {
    if (is_active())
        replay_thread.reset();

    if (do_loop && check_loop.value()) {
        start();
    } else {
        transmitter_model.disable();
        button_play.set_bitmap(&bitmap_play);
        if (file_loaded_)
            text_status.set("armed:ready");
    }

    ready_signal = false;
}

void DroneGeofenceView::handle_replay_thread_done(const uint32_t return_code) {
    if (return_code == ReplayThread::END_OF_FILE) {
        stop(true);
    } else if (return_code == ReplayThread::READ_ERROR) {
        stop(false);
        file_error();
    }

    progressbar.set_value(0);
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
        &option_band,
        &text_status,
        &waterfall,
    });

    // Populate zone selector.
    OptionsField::options_t zone_options;
    for (size_t i = 0; i < zone_count; i++)
        zone_options.emplace_back(zones[i].name, (OptionsField::value_t)i);
    option_zone.set_options(zone_options);
    option_zone.on_change = [this](size_t index, OptionsField::value_t) {
        this->on_zone_changed(index);
    };

    // Populate band selector (GPS L1 C/A first = widest coverage).
    option_band.set_options({
        {"GPS L1", 0},
        {"GLONASS L1", 1},
        {"BeiDou B1", 2},
    });
    option_band.on_change = [this](size_t index, OptionsField::value_t) {
        this->on_band_changed(index);
    };

    field_frequency.set_step(5000);
    field_frequency.set_value(freq_gps_l1);

    button_play.on_select = [this](ImageButton&) {
        this->toggle();
    };

    button_help.on_select = [this](Button&) {
        this->show_zone_help();
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

    set_file_loaded(false);
    on_zone_changed(0);
}

DroneGeofenceView::~DroneGeofenceView() {
    transmitter_model.disable();
    baseband::shutdown();
}

void DroneGeofenceView::on_hide() {
    // TODO: Terrible kludge because widget system doesn't notify Waterfall that
    // it's being shown or hidden.
    if (is_active())
        stop(false);
    waterfall.on_hide();
    View::on_hide();
}

void DroneGeofenceView::set_parent_rect(const Rect new_parent_rect) {
    View::set_parent_rect(new_parent_rect);

    const ui::Rect waterfall_rect{0, header_height, new_parent_rect.width(), new_parent_rect.height() - header_height};
    waterfall.set_parent_rect(waterfall_rect);
}

} /* namespace ui::external_app::drone_geofence */
