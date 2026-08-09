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

/* ---------------------------------------------------------------------------
 * SCOPE - read this before extending the app.
 *
 * This is a bench signal generator for ultra-narrowband (UNB) 2-FSK, using the
 * physical-layer parameters that are publicly confirmed for the Telensa PLANet
 * street-lighting link (FCC ID XYD-2N4D test report: FSK, 500 bps, 25 kHz
 * channel raster, FHSS, ~400 ms bursts).
 *
 * It is NOT a PLANet protocol implementation and does not emit valid PLANet
 * frames. The PLANet frame structure - preamble, sync word, addressing, CRC,
 * FEC, whitening and key management - is proprietary and has never been
 * published. Nothing in this file is derived from a captured or reversed
 * PLANet frame; the framing below is a deliberately generic, user-configurable
 * placeholder so the generator produces a *known* waveform for receiver and
 * capture-chain calibration.
 *
 * If real framing is ever established by measurement, it belongs in a new
 * encoder alongside build_frame(), NOT by quietly redefining these defaults.
 * Keep the placeholder honest and clearly labelled.
 *
 * Two parameters below are inferences, not vendor statements, and are exposed
 * as editable fields rather than baked in as constants:
 *   - The Asia/"S-variant" 920-925 MHz band plan is inferred from Hong Kong
 *     spectrum regulation (HKCA 1049/1078), not published by Telensa.
 *   - The FSK deviation is not published at all. The default here is a guess
 *     from the basestation sensitivity figure; measure it and change it.
 * ------------------------------------------------------------------------ */

#ifndef __TELENSA_H__
#define __TELENSA_H__

#include <cstdint>
#include <cstddef>

namespace ui::external_app::telensa_tx {

/* proc_fsk runs its baseband thread at this rate. samples_per_bit is derived
 * from it, so any change here must track firmware/baseband/proc_fsk.hpp. */
#define UNB_BASEBAND_RATE 2280000U

/* proc_fsk.cpp sets `length = message.stream_length + 32`, so it clocks out 32
 * bits past the end of the supplied stream. We zero-pad by this much so the
 * tail is a defined symbol rather than whatever was left in shared memory. */
#define UNB_PROC_FSK_TAIL_BITS 32

#define UNB_CHANNEL_SPACING 25000U

/* Deviation is unpublished. This default corresponds to a modulation index of
 * ~0.5 at 500 bps, which is the reading consistent with the -139 dBm
 * basestation sensitivity in a ~500 Hz noise bandwidth. Treat as a starting
 * point for measurement, not as fact. */
#define UNB_DEFAULT_DEVIATION 125
#define UNB_DEFAULT_SYMBOL_RATE 500

/* Payload entry width, in hex symbols (nibbles). */
#define UNB_PAYLOAD_NIBBLES 16
#define UNB_MAX_PAYLOAD_BYTES (UNB_PAYLOAD_NIBBLES / 2)

enum band_plan_t {
    BAND_HK = 0,  // Asia / S-variant, inferred
    BAND_US = 1,  // FCC variant, confirmed by test report
    BAND_EU = 2   // ETSI variant, confirmed by BS4 manual
};

struct band_def_t {
    const char* name;
    uint64_t base_hz;      // Centre frequency of channel 0
    uint32_t channel_count;
};

/* Channel 0 centres sit half a raster step inside the band edge, mirroring the
 * FCC variant's published plan (910.4875 MHz = 910.5 - 12.5 kHz). */
extern const band_def_t band_defs[3];

/* Centre frequency of a channel within a band plan. Clamps out-of-range. */
uint64_t channel_frequency(band_plan_t band, uint32_t channel);

/* Builds [preamble 0x55 x n][sync hi][sync lo][payload] into the baseband
 * buffer and zero-pads the proc_fsk tail. Returns the stream length in bits.
 *
 * The 0x55 preamble and 16-bit sync word are conventional placeholders chosen
 * to be easy to find in a capture (0x55 demodulates to a clean tone at half
 * the symbol rate), not PLANet values. */
size_t build_frame(
    uint8_t preamble_bytes,
    uint16_t sync_word,
    const uint8_t* payload,
    size_t payload_len);

/* Pseudo-random hop sequence. 15.247 requires a pseudo-random channel list
 * with roughly equal average use; this is a 16-bit Galois LFSR reduced modulo
 * the channel count, which satisfies that for bench purposes. It is NOT an
 * attempt to reproduce Telensa's hop generator, which is unpublished. */
class HopSequencer {
   public:
    void reset(uint16_t seed = 0xACE1);
    uint32_t next(uint32_t channel_count);

   private:
    uint16_t lfsr_{0xACE1};
};

}  // namespace ui::external_app::telensa_tx

#endif /*__TELENSA_H__*/
