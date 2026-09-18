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

#ifndef __WALKIE_PRESETS_H__
#define __WALKIE_PRESETS_H__

#include <cstddef>
#include <cstdint>

namespace ui::external_app::walkie_rx {

/* NBFM demodulator configuration index (see receiver_model.cpp nbfm_configs):
 *   0 = 8k5, 1 = 11k, 2 = 12k5, 3 = 16k.
 * "Narrow" radios (12.5 kHz channel spacing, 2.5 kHz deviation) use 12k5,
 * "Wide" radios (25 kHz spacing, 5 kHz deviation) use 16k. MURS channels
 * 1-3 are limited to 11.25 kHz occupied bandwidth, so they use 11k. */
constexpr uint8_t BW_11K = 1;
constexpr uint8_t BW_NARROW = 2;
constexpr uint8_t BW_WIDE = 3;

/* DCS code flag: bit 15 set means inverted polarity ("I" suffix). */
constexpr uint16_t DCS_INV = 0x8000;
constexpr uint16_t DCS_CODE_MASK = 0x7FFF;

struct WalkieChannel {
    uint8_t number;      // Channel slot as printed on / shown by the radio.
    uint8_t bw;          // NBFM configuration index (BW_* above).
    uint16_t ctcss_x10;  // CTCSS tone in 0.1 Hz units, 0 = none.
    uint16_t dcs;        // DCS code (decimal digits of the octal code), 0 = none.
    uint32_t freq_hz;    // Channel centre frequency.
};

struct WalkieRadio {
    char name[18];           // "Brand Model", max 17 chars (options field width).
    char channel_prefix[6];  // Printed before the slot number, e.g. "CH".
    uint8_t squelch;         // PortaPack NBFM squelch level 0..99.
    uint8_t channel_count;
    const WalkieChannel* channels;
};

extern const WalkieRadio walkie_radios[];
extern const size_t walkie_radio_count;

}  // namespace ui::external_app::walkie_rx

#endif /* __WALKIE_PRESETS_H__ */
