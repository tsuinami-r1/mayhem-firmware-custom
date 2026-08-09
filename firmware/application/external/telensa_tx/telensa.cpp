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

#include "telensa.hpp"
#include "portapack_shared_memory.hpp"

#include <cstring>

namespace ui::external_app::telensa_tx {

const band_def_t band_defs[3] = {
    /* Asia / S-variant. INFERRED from HK regulation (920-925 MHz licence-exempt
     * SRD, HKCA 1049/1078), not published by Telensa. 200 channels, each at
     * least 12.5 kHz clear of a band edge. */
    {"HK 920-925", 920012500ULL, 200},

    /* FCC variant. Confirmed: FCC ID XYD-2N4D test report gives an occupied
     * band of 910.4875-919.9875 MHz on a 25 kHz raster. */
    {"US 910-920", 910487500ULL, 381},

    /* ETSI variant. Confirmed: BS4 manual EU TX table, 869.40-869.650 MHz. */
    {"EU 869.4", 869412500ULL, 10}};

uint64_t channel_frequency(band_plan_t band, uint32_t channel) {
    const auto& def = band_defs[band];

    if (channel >= def.channel_count)
        channel = def.channel_count - 1;

    return def.base_hz + ((uint64_t)channel * UNB_CHANNEL_SPACING);
}

size_t build_frame(
    uint8_t preamble_bytes,
    uint16_t sync_word,
    const uint8_t* payload,
    size_t payload_len) {
    uint8_t* buffer = shared_memory.bb_data.data;
    size_t offset = 0;

    /* 0x55 gives an alternating bit pattern, which demodulates to a clean tone
     * at half the symbol rate - the easiest thing to lock onto in a capture. */
    for (uint8_t c = 0; c < preamble_bytes; c++)
        buffer[offset++] = 0x55;

    buffer[offset++] = (sync_word >> 8) & 0xFF;
    buffer[offset++] = sync_word & 0xFF;

    for (size_t c = 0; c < payload_len; c++)
        buffer[offset++] = payload[c];

    /* Cover proc_fsk's 32-bit overrun with a defined symbol. */
    memset(&buffer[offset], 0, UNB_PROC_FSK_TAIL_BITS / 8);

    return offset * 8;
}

void HopSequencer::reset(uint16_t seed) {
    // An all-zero state is a fixed point for an LFSR; substitute the default.
    lfsr_ = seed ? seed : 0xACE1;
}

uint32_t HopSequencer::next(uint32_t channel_count) {
    if (!channel_count) return 0;

    // Galois LFSR, x^16 + x^14 + x^13 + x^11 + 1.
    uint16_t lsb = lfsr_ & 1;
    lfsr_ >>= 1;
    if (lsb) lfsr_ ^= 0xB400;

    return lfsr_ % channel_count;
}

}  // namespace ui::external_app::telensa_tx
