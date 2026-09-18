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

#include "ui.hpp"
#include "ui_walkie_rx.hpp"
#include "ui_navigation.hpp"
#include "external_app.hpp"

namespace ui::external_app::walkie_rx {
void initialize_app(ui::NavigationView& nav) {
    nav.push<WalkieRxView>();
}
}  // namespace ui::external_app::walkie_rx

extern "C" {

__attribute__((section(".external_app.app_walkie_rx.application_information"), used)) application_information_t _application_information_walkie_rx = {
    /*.memory_location = */ (uint8_t*)0x00000000,
    /*.externalAppEntry = */ ui::external_app::walkie_rx::initialize_app,
    /*.header_version = */ CURRENT_HEADER_VERSION,
    /*.app_version = */ VERSION_MD5,

    /*.app_name = */ "Walkie-Talkie",
    /*.bitmap_data = */ {
        // 16x16, one row per byte pair, LSB = leftmost pixel.
        // Antenna on the top left, display, speaker grille, PTT bump.
        0x10,
        0x00,
        0x10,
        0x00,
        0x10,
        0x00,
        0x10,
        0x00,
        0xF8,
        0x1F,
        0xE8,
        0x17,
        0xE8,
        0x17,
        0x08,
        0x10,
        0xF8,
        0x1F,
        0xAC,
        0x1A,
        0x4C,
        0x15,
        0xAC,
        0x1A,
        0x48,
        0x15,
        0xA8,
        0x1A,
        0x08,
        0x10,
        0xF8,
        0x1F,
    },
    /*.icon_color = */ ui::Color::green().v,
    /*.menu_location = */ app_location_t::RX,
    /*.desired_menu_position = */ -1,

    /*.m4_app_tag = portapack::spi_flash::image_tag_nfm_audio */ {'P', 'N', 'F', 'M'},
    /*.m4_app_offset = */ 0x00000000,  // will be filled at compile time
};
}
