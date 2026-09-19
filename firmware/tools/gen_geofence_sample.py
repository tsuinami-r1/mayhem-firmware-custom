#!/usr/bin/env python3
#
# Copyright (C) 2026 Claude / PortaPack contributors
#
# This file is part of PortaPack.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#

"""
Generate a small GPS L1 C/A baseband SAMPLE for the Drone Geofence TX app.

This produces a deterministic .C8 file (interleaved int8 I/Q, "sc8") at the
2.6 MHz sample rate the app replays, filled with real GPS L1 C/A Gold-code
BPSK for a handful of PRNs.

It is a TEST VECTOR only: there is no navigation-message data, no per-satellite
Doppler and no correct inter-satellite code-phase/pseudorange alignment, so a
GPS receiver CANNOT compute a position (and therefore no real "Hong Kong"
geofence) from it. Its purpose is to exercise the app end to end - file open,
duration/sample-rate display, replay start/stop/loop and the L1 spectrum on the
waterfall - on the bench.

For a scenario that actually places a receiver at a no-fly-zone coordinate,
regenerate with gps-sdr-sim using the command the app shows under "?".

Each band is written as <zone>_<band>.C8 with a matching .TXT carrying that
band's centre frequency, which is the layout the app's band-hopping engine
looks for in the GEOFENCE folder.

Usage:
    python3 gen_geofence_sample.py [out_dir] [zone] [bands] [duration_ms]
    (defaults: ../../sdcard/GEOFENCE, HKG, "L1,L5", 200 ms)

    Full hop set:
    python3 gen_geofence_sample.py . HKG L1,B1I,GLON,L5,L2C
"""

import os
import sys
import struct

FS = 2600000          # sample rate (Hz) - must match the app's replay rate
CHIP_RATE = 1023000   # GPS L1 C/A chipping rate (chips/s)
CODE_LEN = 1023       # chips per C/A code period (1 ms)

# G2 phase-selector tap pairs (1-indexed) per PRN, from the GPS ICD.
G2_TAPS = {
    1: (2, 6), 2: (3, 7), 3: (4, 8), 4: (5, 9), 5: (1, 9),
    6: (2, 10), 7: (1, 8), 8: (2, 9), 9: (3, 10), 10: (2, 3),
    11: (3, 4), 12: (5, 6), 13: (6, 7), 14: (7, 8), 15: (8, 9),
    16: (9, 10), 17: (1, 4), 18: (2, 5), 19: (3, 6), 20: (4, 7),
    21: (5, 8), 22: (6, 9), 23: (1, 3), 24: (4, 6), 25: (5, 7),
    26: (6, 8), 27: (7, 9), 28: (8, 10), 29: (1, 6), 30: (2, 7),
    31: (3, 8), 32: (4, 9),
}


def ca_code(prn):
    """Return the 1023-chip C/A code for a PRN as a list of 0/1 ints."""
    g1 = [1] * 10
    g2 = [1] * 10
    tap0, tap1 = G2_TAPS[prn]
    out = []
    for _ in range(CODE_LEN):
        # G2i is the modulo-2 sum of the two selected G2 stages.
        g2i = g2[tap0 - 1] ^ g2[tap1 - 1]
        out.append(g1[9] ^ g2i)

        # G1: feedback taps 3 and 10.
        fb1 = g1[2] ^ g1[9]
        # G2: feedback taps 2,3,6,8,9,10.
        fb2 = g2[1] ^ g2[2] ^ g2[5] ^ g2[7] ^ g2[8] ^ g2[9]

        g1 = [fb1] + g1[:9]
        g2 = [fb2] + g2[:9]
    return out


# Centre frequency per band, matching the app's band table in
# ui_drone_geofence.cpp. Used only for the sidecar metadata.
BAND_FREQ = {
    "L1": 1575420000,    # GPS L1 C/A + Galileo E1 + BeiDou B1C + QZSS L1
    "B1I": 1561098000,   # BeiDou B1I
    "GLON": 1602000000,  # GLONASS L1 (FDMA centre)
    "L5": 1176450000,    # GPS L5 + Galileo E5a + BeiDou B2a
    "L2C": 1227600000,   # GPS L2C
}


def write_band(out_path, band, duration_ms, prns):
    """Write one <zone>_<band>.C8 test vector plus its .TXT metadata."""
    codes = {p: ca_code(p) for p in prns}

    n_samples = int(round(FS * duration_ms / 1000.0))
    amp = 26                      # per-PRN BPSK amplitude (sum stays within int8)
    rng = 0x1234ABCD              # deterministic LCG state for low-level noise

    buf = bytearray(n_samples * 2)
    for n in range(n_samples):
        t = n / FS
        chip = int(t * CHIP_RATE) % CODE_LEN
        acc = 0
        for p in prns:
            # BPSK: 0 -> +1, 1 -> -1
            acc += amp if codes[p][chip] == 0 else -amp

        # Small deterministic dither so quiet spans aren't perfectly flat.
        rng = (1103515245 * rng + 12345) & 0x7FFFFFFF
        noise = ((rng >> 16) % 7) - 3

        i = max(-127, min(127, acc + noise))
        rng = (1103515245 * rng + 12345) & 0x7FFFFFFF
        q = ((rng >> 16) % 7) - 3   # BPSK power is on I; Q carries only dither

        buf[2 * n] = struct.pack("b", i)[0]
        buf[2 * n + 1] = struct.pack("b", q)[0]

    out_path = os.path.normpath(out_path)
    with open(out_path, "wb") as f:
        f.write(buf)

    # Sidecar metadata so the app shows the right sample rate / duration.
    meta_path = os.path.splitext(out_path)[0] + ".TXT"
    with open(meta_path, "w") as f:
        f.write("sample_rate=%d\n" % FS)
        f.write("center_frequency=%d\n" % BAND_FREQ[band])

    print("Wrote %s (%d bytes, %.0f ms, band %s, PRNs %s)" % (
        out_path, len(buf), duration_ms, band, prns))
    print("Wrote %s" % meta_path)


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "..", "sdcard", "GEOFENCE")
    zone = sys.argv[2] if len(sys.argv) > 2 else "HKG"
    # Bands to emit. L1 and L5 ship as samples; pass more on the command line
    # (e.g. "L1,B1I,GLON,L5,L2C") to generate the full hop set.
    band_list = (sys.argv[3] if len(sys.argv) > 3 else "L1,L5").split(",")
    duration_ms = float(sys.argv[4]) if len(sys.argv) > 4 else 200.0

    # A few "visible" satellites for a realistic spread-spectrum shape. Distinct
    # PRN sets per band so the hop is visually distinguishable on a waterfall.
    prn_sets = {
        "L1": [1, 11, 17, 22],
        "B1I": [2, 12, 18, 23],
        "GLON": [3, 13, 19, 24],
        "L5": [5, 15, 20, 26],
        "L2C": [7, 16, 21, 28],
    }

    for band in band_list:
        band = band.strip()
        if band not in BAND_FREQ:
            print("Unknown band %r (known: %s)" % (
                band, ",".join(sorted(BAND_FREQ))))
            sys.exit(2)
        path = os.path.join(out_dir, "%s_%s.C8" % (zone, band))
        write_band(path, band, duration_ms, prn_sets[band])


if __name__ == "__main__":
    main()
