/*
 * Copyright (C) 2023 Bernd Herzog
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

#include "ui.hpp"
#include "ui_drone_geofence.hpp"
#include "ui_navigation.hpp"
#include "external_app.hpp"

namespace ui::external_app::drone_geofence {
void initialize_app(ui::NavigationView& nav) {
    nav.push<DroneGeofenceView>();
}
}  // namespace ui::external_app::drone_geofence

extern "C" {

__attribute__((section(".external_app.app_drone_geofence.application_information"), used)) application_information_t _application_information_drone_geofence = {
    /*.memory_location = */ (uint8_t*)0x00000000,
    /*.externalAppEntry = */ ui::external_app::drone_geofence::initialize_app,
    /*.header_version = */ CURRENT_HEADER_VERSION,
    /*.app_version = */ VERSION_MD5,

    /*.app_name = */ "Geofence TX",
    /*.bitmap_data = */ {
        0x00,
        0x00,
        0xE0,
        0x07,
        0xF8,
        0x1F,
        0x1C,
        0x38,
        0x3C,
        0x30,
        0x76,
        0x60,
        0xE6,
        0x60,
        0xC6,
        0x61,
        0x86,
        0x63,
        0x06,
        0x67,
        0x06,
        0x6E,
        0x0C,
        0x3C,
        0x1C,
        0x38,
        0xF8,
        0x1F,
        0xE0,
        0x07,
        0x00,
        0x00,
    },
    /*.icon_color = */ ui::Color::red().v,
    /*.menu_location = */ app_location_t::TX,
    /*.desired_menu_position = */ -1,

    /*.m4_app_tag = portapack::spi_flash::image_tag_gpssim */ {'P', 'G', 'P', 'S'},
    /*.m4_app_offset = */ 0x00000000,  // will be filled at compile time
};
}
