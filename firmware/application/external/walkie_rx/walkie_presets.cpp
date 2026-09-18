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

/*
 * Factory-default channel plans of common analog FM walkie-talkies.
 *
 * Every entry is the frequency, tone squelch and bandwidth the radio ships
 * with in the given channel slot, so selecting "Brand Model / CH n" tunes the
 * HackRF exactly like a factory-fresh unit sitting on that channel.
 *
 * Sources (all public):
 *  - Baofeng BF-888S, UV-5R/UV-82, Retevis H-777:
 *      RadioReference wiki "CCR Default Frequencies" and the CHIRP dump at
 *      gist.github.com/kennedy/11278351. The BF-888S list is "variant 1",
 *      the most common one, which matches the CHIRP dump.
 *  - Motorola business radios (CLS/RMU/RDU/RMV/RDV):
 *      buytwowayradios.com "Default Frequencies for Motorola Business Radios"
 *      (derived from the Motorola user guides).
 *  - FRS/GMRS 22-channel plan (Motorola Talkabout, Midland, Cobra, ...):
 *      47 CFR 95 subpart B; Motorola Talkabout channel chart. Consumer FRS
 *      radios ship on channel 1 with interference eliminator code 0 (no tone).
 *  - PMR446 16-channel plan (Motorola T82/TLKR, Baofeng BF-88E, ...):
 *      ECC/DEC(15)05, 446.00625 MHz + n * 12.5 kHz.
 *  - MURS (Motorola RMM2050): 47 CFR 95 subpart J. Channels 1-3 are limited
 *      to 11.25 kHz, channels 4-5 to 20 kHz.
 *
 * Notes on what is *not* verified from a factory dump:
 *  - Squelch: PortaPack's 0..99 NBFM squelch has no direct mapping to a
 *    walkie's 0..9 setting. Baofeng ships at SQL 5 (-> 55), Motorola business
 *    and consumer radios use a fixed/auto squelch (-> 60).
 *  - RMM2050 default interference eliminator code is not published in the
 *    sources above; it is stored here as "no tone".
 */

#include "walkie_presets.hpp"

namespace ui::external_app::walkie_rx {

#define CT(n, bw, hz, tone_x10) \
    {n, bw, tone_x10, 0, hz}
#define DC(n, bw, hz, code) \
    {n, bw, 0, code, hz}
#define NT(n, bw, hz) \
    {n, bw, 0, 0, hz}

/* Baofeng BF-888S (and BF-666S/BF-777S, most 888S clones). Wide FM. */
static const WalkieChannel bf888s_channels[] = {
    CT(1, BW_WIDE, 462'125'000, 693),
    NT(2, BW_WIDE, 462'225'000),
    NT(3, BW_WIDE, 462'325'000),
    CT(4, BW_WIDE, 462'425'000, 1035),
    CT(5, BW_WIDE, 462'525'000, 1148),
    CT(6, BW_WIDE, 462'625'000, 1273),
    CT(7, BW_WIDE, 462'725'000, 1365),
    CT(8, BW_WIDE, 462'825'000, 1622),
    DC(9, BW_WIDE, 462'925'000, 25),
    DC(10, BW_WIDE, 463'025'000, 51),
    DC(11, BW_WIDE, 463'125'000, 125),
    DC(12, BW_WIDE, 463'225'000, 155 | DCS_INV),
    DC(13, BW_WIDE, 463'525'000, 465 | DCS_INV),
    DC(14, BW_WIDE, 450'225'000, 23),
    NT(15, BW_WIDE, 460'325'000),
    CT(16, BW_WIDE, 469'950'000, 2035),
};

/* Baofeng UV-5R / UV-82 / BF-F8HP family, factory image up to ~2018
 * (firmware before HN5RV01). Channel 0 is the VFO-A default. Wide FM. */
static const WalkieChannel uv5r_channels[] = {
    NT(0, BW_WIDE, 136'025'000),
    CT(1, BW_WIDE, 452'125'000, 693),
    CT(2, BW_WIDE, 453'225'000, 915),
    CT(3, BW_WIDE, 454'325'000, 1365),
    CT(4, BW_WIDE, 455'425'000, 1514),
    CT(5, BW_WIDE, 456'525'000, 1928),
    CT(6, BW_WIDE, 457'625'000, 2418),
    DC(7, BW_WIDE, 458'725'000, 25),
    DC(8, BW_WIDE, 459'825'000, 134),
    DC(9, BW_WIDE, 461'925'000, 274),
    DC(10, BW_WIDE, 462'225'000, 346),
    DC(11, BW_WIDE, 463'325'000, 503),
    DC(12, BW_WIDE, 464'425'000, 73 | DCS_INV),
    DC(13, BW_WIDE, 465'525'000, 703 | DCS_INV),
    NT(14, BW_WIDE, 402'225'000),
    NT(15, BW_WIDE, 437'425'000),
    NT(16, BW_WIDE, 479'975'000),
    NT(17, BW_WIDE, 138'550'000),
    NT(18, BW_WIDE, 157'650'000),
    NT(19, BW_WIDE, 172'750'000),
    NT(20, BW_WIDE, 438'500'000),
    NT(21, BW_WIDE, 155'700'000),
    NT(127, BW_WIDE, 470'625'000),
};

/* Baofeng UV-5R family shipped after ~2018 (firmware HN5RV01 and later):
 * only the two VFO defaults are programmed. */
static const WalkieChannel uv5r_new_channels[] = {
    NT(0, BW_WIDE, 144'725'000),
    NT(127, BW_WIDE, 435'725'000),
};

/* Retevis H-777 (BF-888S hardware clone with its own factory plan). */
static const WalkieChannel h777_channels[] = {
    CT(1, BW_WIDE, 456'650'000, 670),
    NT(2, BW_WIDE, 456'650'000),
    CT(3, BW_WIDE, 462'487'500, 670),
    NT(4, BW_WIDE, 462'412'500),
    NT(5, BW_WIDE, 462'312'500),
    NT(6, BW_WIDE, 462'187'500),
    NT(7, BW_WIDE, 462'037'500),
    NT(8, BW_WIDE, 461'862'500),
    NT(9, BW_WIDE, 461'662'500),
    NT(10, BW_WIDE, 461'437'500),
    NT(11, BW_WIDE, 461'187'500),
    NT(12, BW_WIDE, 460'912'500),
    NT(13, BW_WIDE, 460'612'500),
    NT(14, BW_WIDE, 462'562'500),
    NT(15, BW_WIDE, 420'937'500),
    NT(16, BW_WIDE, 456'650'000),
};

/* FRS/GMRS 22-channel plan used by every North-American consumer walkie
 * (Motorola Talkabout T-series, Midland, Cobra, Uniden, ...). All FRS
 * channels are narrowband (12.5 kHz). Factory default: no tone. */
static const WalkieChannel frs_channels[] = {
    NT(1, BW_NARROW, 462'562'500),
    NT(2, BW_NARROW, 462'587'500),
    NT(3, BW_NARROW, 462'612'500),
    NT(4, BW_NARROW, 462'637'500),
    NT(5, BW_NARROW, 462'662'500),
    NT(6, BW_NARROW, 462'687'500),
    NT(7, BW_NARROW, 462'712'500),
    NT(8, BW_NARROW, 467'562'500),
    NT(9, BW_NARROW, 467'587'500),
    NT(10, BW_NARROW, 467'612'500),
    NT(11, BW_NARROW, 467'637'500),
    NT(12, BW_NARROW, 467'662'500),
    NT(13, BW_NARROW, 467'687'500),
    NT(14, BW_NARROW, 467'712'500),
    NT(15, BW_NARROW, 462'550'000),
    NT(16, BW_NARROW, 462'575'000),
    NT(17, BW_NARROW, 462'600'000),
    NT(18, BW_NARROW, 462'625'000),
    NT(19, BW_NARROW, 462'650'000),
    NT(20, BW_NARROW, 462'675'000),
    NT(21, BW_NARROW, 462'700'000),
    NT(22, BW_NARROW, 462'725'000),
};

/* PMR446 16-channel plan (Europe). Channels 9-16 were added in 2018 and are
 * only present on newer radios. Narrowband, factory default: no tone. */
static const WalkieChannel pmr446_channels[] = {
    NT(1, BW_NARROW, 446'006'250),
    NT(2, BW_NARROW, 446'018'750),
    NT(3, BW_NARROW, 446'031'250),
    NT(4, BW_NARROW, 446'043'750),
    NT(5, BW_NARROW, 446'056'250),
    NT(6, BW_NARROW, 446'068'750),
    NT(7, BW_NARROW, 446'081'250),
    NT(8, BW_NARROW, 446'093'750),
    NT(9, BW_NARROW, 446'106'250),
    NT(10, BW_NARROW, 446'118'750),
    NT(11, BW_NARROW, 446'131'250),
    NT(12, BW_NARROW, 446'143'750),
    NT(13, BW_NARROW, 446'156'250),
    NT(14, BW_NARROW, 446'168'750),
    NT(15, BW_NARROW, 446'181'250),
    NT(16, BW_NARROW, 446'193'750),
};

/* Motorola CLS1110 (ch 1 only) / CLS1410 (ch 1-4). Code 1 = 67.0 Hz. */
static const WalkieChannel cls_channels[] = {
    CT(1, BW_NARROW, 464'550'000, 670),
    CT(2, BW_NARROW, 467'925'000, 670),
    CT(3, BW_NARROW, 467'850'000, 670),
    CT(4, BW_NARROW, 467'875'000, 670),
};

/* Motorola RMU2040 / RMU2080 / RMU2080d / RDU2020 / RDU2080d (UHF).
 * RDU2020 uses the first two slots, RMU2040 the first four. */
static const WalkieChannel rmu_channels[] = {
    CT(1, BW_NARROW, 464'550'000, 670),
    CT(2, BW_NARROW, 467'925'000, 670),
    CT(3, BW_NARROW, 467'850'000, 670),
    CT(4, BW_NARROW, 467'875'000, 670),
    CT(5, BW_NARROW, 461'062'500, 670),
    CT(6, BW_NARROW, 461'112'500, 670),
    CT(7, BW_NARROW, 461'162'500, 670),
};

/* Motorola RMV2080 / RDV2020 / RDV2080d (VHF). */
static const WalkieChannel rmv_channels[] = {
    CT(1, BW_NARROW, 154'490'000, 670),
    CT(2, BW_NARROW, 154'515'000, 670),
    CT(3, BW_NARROW, 151'625'000, 670),
    CT(4, BW_NARROW, 151'955'000, 670),
    CT(5, BW_NARROW, 151'512'500, 670),
    CT(6, BW_NARROW, 151'685'000, 670),
    CT(7, BW_NARROW, 151'775'000, 670),
};

/* Motorola RDU4100 / RDU4160d (UHF 4 W): two frequencies, five codes each. */
static const WalkieChannel rdu4100_channels[] = {
    CT(1, BW_NARROW, 464'500'000, 670),
    CT(2, BW_NARROW, 464'500'000, 770),
    CT(3, BW_NARROW, 464'500'000, 885),
    CT(4, BW_NARROW, 464'500'000, 1799),
    NT(5, BW_NARROW, 464'500'000),
    CT(6, BW_NARROW, 464'550'000, 670),
    CT(7, BW_NARROW, 464'550'000, 825),
    CT(8, BW_NARROW, 464'550'000, 948),
    CT(9, BW_NARROW, 464'550'000, 1799),
    NT(10, BW_NARROW, 464'550'000),
};

/* Motorola RDV5100 (VHF 5 W). */
static const WalkieChannel rdv5100_channels[] = {
    CT(1, BW_NARROW, 151'625'000, 670),
    CT(2, BW_NARROW, 151'625'000, 770),
    CT(3, BW_NARROW, 151'625'000, 885),
    CT(4, BW_NARROW, 151'625'000, 1799),
    NT(5, BW_NARROW, 151'625'000),
    CT(6, BW_NARROW, 151'955'000, 670),
    CT(7, BW_NARROW, 151'955'000, 825),
    CT(8, BW_NARROW, 151'955'000, 948),
    CT(9, BW_NARROW, 151'955'000, 1799),
    NT(10, BW_NARROW, 151'955'000),
};

/* MURS (Motorola RMM2050, Dakota Alert, ...): 5 slots = MURS 1-5. */
static const WalkieChannel murs_channels[] = {
    NT(1, BW_11K, 151'820'000),
    NT(2, BW_11K, 151'880'000),
    NT(3, BW_11K, 151'940'000),
    NT(4, BW_WIDE, 154'570'000),
    NT(5, BW_WIDE, 154'600'000),
};

#define RADIO(name, prefix, sq, table) \
    {name, prefix, sq, (uint8_t)(sizeof(table) / sizeof(table[0])), table}
#define RADIO_N(name, prefix, sq, table, n) \
    {name, prefix, sq, n, table}

constexpr uint8_t SQ_BAOFENG = 55;   // Baofeng ships at SQL 5 of 9.
constexpr uint8_t SQ_MOTOROLA = 60;  // Fixed/auto squelch on Motorola sets.

const WalkieRadio walkie_radios[] = {
    RADIO("Baofeng BF-888S", "CH", SQ_BAOFENG, bf888s_channels),
    RADIO("Baofeng UV-5R", "CH", SQ_BAOFENG, uv5r_channels),
    RADIO("Baofeng UV-5R 18+", "CH", SQ_BAOFENG, uv5r_new_channels),
    RADIO("Baofeng BF-88E", "PMR", SQ_BAOFENG, pmr446_channels),
    RADIO("Retevis H-777", "CH", SQ_BAOFENG, h777_channels),
    RADIO("Motorola T-series", "CH", SQ_MOTOROLA, frs_channels),
    RADIO("Motorola T82 PMR", "CH", SQ_MOTOROLA, pmr446_channels),
    RADIO("Motorola CLS1410", "CH", SQ_MOTOROLA, cls_channels),
    RADIO_N("Motorola RDU2020", "CH", SQ_MOTOROLA, rmu_channels, 2),
    RADIO("Motorola RMU2080", "CH", SQ_MOTOROLA, rmu_channels),
    RADIO_N("Motorola RDV2020", "CH", SQ_MOTOROLA, rmv_channels, 2),
    RADIO("Motorola RMV2080", "CH", SQ_MOTOROLA, rmv_channels),
    RADIO("Motorola RDU4100", "CH", SQ_MOTOROLA, rdu4100_channels),
    RADIO("Motorola RDV5100", "CH", SQ_MOTOROLA, rdv5100_channels),
    RADIO("Motorola RMM2050", "MURS", SQ_MOTOROLA, murs_channels),
    RADIO("Midland/Cobra FRS", "CH", SQ_MOTOROLA, frs_channels),
};

const size_t walkie_radio_count = sizeof(walkie_radios) / sizeof(walkie_radios[0]);

}  // namespace ui::external_app::walkie_rx
