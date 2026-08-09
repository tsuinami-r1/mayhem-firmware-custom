#!/usr/bin/env python3
"""Wideband channel-occupancy survey and hop-sequence logger.

Answers "which channels are in use, when, and in what order" without storing
terabytes of IQ. A 5 MHz capture at 10 Msps is 20 MB/s — 72 GB/hour, 1.7 TB/day
— which is not a practical way to observe a system that transmits sparsely. This
tool reduces the capture to a detection log of a few kilobytes per hour, and you
keep IQ only for the bursts worth demodulating.

It reads in chunks, so the input file can be far larger than memory.

Channel grid follows the published FCC plan convention: channel 0 sits half a
25 kHz raster step inside the band edge. Note that the Asia/S-variant
920-925 MHz plan is an inference from Hong Kong regulation, not a vendor
statement — pass --base explicitly if you have better information.

Examples
--------
    # Survey a wideband capture against the (inferred) HK plan
    ./unb_survey.py wide.cs16 --sample-rate 10000000 --center 922500000 --band hk

    # Log detections for later hop-sequence analysis
    ./unb_survey.py wide.cs16 --sample-rate 10000000 --center 922500000 \
        --csv detections.csv --hop-report

    # Sanity-check the tool against a synthetic hopping file
    ./unb_selftest.py --out hop.cs16 --bursts 20 --hop --sample-rate 250000
    ./unb_survey.py hop.cs16 --center 920012500 --threshold 8
"""

import argparse
import sys

import numpy as np

import iqio

# Channel-0 centre frequencies. See telensa.hpp for provenance of each.
BAND_PLANS = {
    "hk": ("HK 920-925 (inferred)", 920012500, 200),
    "us": ("US 910.4875-919.9875 (FCC test report)", 910487500, 381),
    "eu": ("EU 869.40-869.65 (BS4 manual)", 869412500, 10),
}


def channel_grid(base_hz, count, spacing=25000):
    return base_hz + np.arange(count) * spacing


def survey(path, args):
    """Chunked spectrogram -> per-channel power over time."""
    centres = channel_grid(args.base, args.channels, args.spacing)

    # Only channels inside the captured bandwidth are observable. Report the
    # shortfall rather than silently surveying a fraction of the band.
    half_span = args.sample_rate / 2
    visible = (centres >= args.center - half_span) & (centres <= args.center + half_span)

    if not np.any(visible):
        print(f"ERROR: no channel of the '{args.band}' plan falls within the captured\n"
              f"band ({(args.center-half_span)/1e6:.4f}-{(args.center+half_span)/1e6:.4f} MHz).\n"
              f"Check --center and --band.", file=sys.stderr)
        return None, None, None

    visible_idx = np.flatnonzero(visible)
    print(f"plan {BAND_PLANS.get(args.band, ('custom',))[0]}")
    print(f"{len(visible_idx)} of {args.channels} channels within the captured bandwidth"
          f" (ch {visible_idx[0]}-{visible_idx[-1]})")

    if len(visible_idx) < args.channels:
        print(f"NOTE: {args.channels - len(visible_idx)} channels are outside the capture."
              f" Stepped sweeps are needed to cover the full plan.")

    fft_size = args.fft_size
    freqs = np.fft.fftshift(np.fft.fftfreq(fft_size, 1 / args.sample_rate)) + args.center

    # Precompute the bin span belonging to each visible channel. Integrating a
    # narrow window around the centre — rather than the whole 25 kHz raster —
    # keeps adjacent-channel energy out. The raster is a hop grid, not the
    # signal bandwidth: occupied bandwidth here is a couple of kHz at most.
    bin_spans = []
    for idx in visible_idx:
        mask = np.abs(freqs - centres[idx]) <= args.integrate_bw / 2
        bin_spans.append(np.flatnonzero(mask))

    if all(len(s) == 0 for s in bin_spans):
        print(f"ERROR: --integrate-bw {args.integrate_bw} Hz is narrower than the FFT bin\n"
              f"spacing ({args.sample_rate/fft_size:.1f} Hz). Raise --fft-size or "
              f"--integrate-bw.", file=sys.stderr)
        return None, None, None

    window = np.hanning(fft_size)
    chunk_frames = max(1, args.chunk_samples // fft_size)

    powers, times = [], []
    offset = 0

    while True:
        capture = iqio.load(
            path, fmt=args.format, sample_rate=args.sample_rate,
            count=chunk_frames * fft_size, offset=offset,
        )
        samples = capture.samples
        if len(samples) < fft_size:
            break

        frames = len(samples) // fft_size
        block = samples[:frames * fft_size].reshape(frames, fft_size) * window
        spectrum = np.abs(np.fft.fftshift(np.fft.fft(block, axis=1), axes=1)) ** 2

        frame_power = np.empty((frames, len(visible_idx)), dtype=np.float32)
        for column, span in enumerate(bin_spans):
            frame_power[:, column] = (
                spectrum[:, span].sum(axis=1) if len(span) else 0.0
            )

        powers.append(frame_power)
        times.append((offset + np.arange(frames) * fft_size) / args.sample_rate)

        offset += frames * fft_size
        if args.max_seconds and offset / args.sample_rate >= args.max_seconds:
            break

    if not powers:
        print("ERROR: capture too short to analyse.", file=sys.stderr)
        return None, None, None

    return np.vstack(powers), np.concatenate(times), visible_idx


def find_detections(power_db, times, visible_idx, centres, args):
    """Group per-channel threshold crossings into bursts."""
    detections = []
    frame_ms = (times[1] - times[0]) * 1000 if len(times) > 1 else 0.0

    for column, channel in enumerate(visible_idx):
        track = power_db[:, column]

        # Per-channel floor: a narrowband interferer parked on one channel
        # should not raise the threshold for its neighbours.
        floor = np.median(track)
        above = track > (floor + args.threshold)
        if not np.any(above):
            continue

        edges = np.diff(above.astype(np.int8))
        starts = list(np.flatnonzero(edges == 1) + 1)
        ends = list(np.flatnonzero(edges == -1) + 1)
        if above[0]:
            starts.insert(0, 0)
        if above[-1]:
            ends.append(len(above))

        for start, end in zip(starts, ends):
            duration_ms = (end - start) * frame_ms
            if duration_ms < args.min_duration:
                continue
            detections.append({
                "time_s": float(times[start]),
                "channel": int(channel),
                "freq_hz": float(centres[channel]),
                "power_db": float(np.max(track[start:end]) - floor),
                "duration_ms": float(duration_ms),
            })

    detections.sort(key=lambda d: d["time_s"])
    return detections


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("capture", help="wideband IQ capture")
    parser.add_argument("--format", help="cs8 / cu8 / cs16 / cf32")
    parser.add_argument("--sample-rate", type=float, help="sample rate (Hz)")
    parser.add_argument("--center", type=float, help="capture centre frequency (Hz)")
    parser.add_argument("--band", default="hk", choices=sorted(BAND_PLANS) + ["custom"],
                        help="channel plan (default hk)")
    parser.add_argument("--base", type=float, help="channel 0 centre (Hz), overrides --band")
    parser.add_argument("--channels", type=int, help="channel count, overrides --band")
    parser.add_argument("--spacing", type=float, default=25000, help="channel raster (Hz)")
    parser.add_argument("--fft-size", type=int, default=8192,
                        help="FFT length. Larger = finer RBW, coarser time resolution. "
                             "Set RBW to hundreds of Hz, not tens of kHz — a coarse sweep "
                             "misses these signals entirely")
    parser.add_argument("--integrate-bw", type=float, default=4000,
                        help="bandwidth integrated per channel (Hz)")
    parser.add_argument("--threshold", type=float, default=10.0,
                        help="detection threshold above each channel's own floor (dB)")
    parser.add_argument("--min-duration", type=float, default=50.0,
                        help="ignore detections shorter than this (ms)")
    parser.add_argument("--chunk-samples", type=int, default=1 << 22,
                        help="samples per read; bounds memory use on huge files")
    parser.add_argument("--max-seconds", type=float, default=0.0,
                        help="stop after this many seconds (0 = whole file)")
    parser.add_argument("--csv", help="write detections to this CSV")
    parser.add_argument("--hop-report", action="store_true",
                        help="report the channel visit order and revisit intervals")
    args = parser.parse_args()

    if args.band != "custom":
        _, default_base, default_count = BAND_PLANS[args.band]
        args.base = args.base if args.base is not None else default_base
        args.channels = args.channels if args.channels is not None else default_count
    if args.base is None or args.channels is None:
        parser.error("--band custom requires both --base and --channels")

    probe = iqio.load(args.capture, fmt=args.format, sample_rate=args.sample_rate, count=1)
    args.sample_rate = args.sample_rate or probe.sample_rate
    if args.center is None:
        args.center = probe.center_freq
    if args.center is None:
        parser.error("--center is required (no SigMF metadata found)")

    rbw = args.sample_rate / args.fft_size
    print(f"RBW {rbw:.1f} Hz, time resolution {args.fft_size/args.sample_rate*1000:.1f} ms")
    if rbw > 1000:
        print(f"WARNING: RBW {rbw:.0f} Hz is coarse for a ~500 bps signal. Raise --fft-size.")

    power, times, visible_idx = survey(args.capture, args)
    if power is None:
        return 1

    power_db = 10 * np.log10(power + 1e-20)
    centres = channel_grid(args.base, args.channels, args.spacing)
    detections = find_detections(power_db, times, visible_idx, centres, args)

    print(f"\nanalysed {times[-1]:.2f} s, {len(detections)} detection(s)\n")

    for det in detections[:40]:
        print(f"  t={det['time_s']:9.3f}s  ch{det['channel']:4d}  "
              f"{det['freq_hz']/1e6:10.4f} MHz  "
              f"{det['power_db']:5.1f} dB  {det['duration_ms']:7.1f} ms")
    if len(detections) > 40:
        print(f"  ... {len(detections)-40} more (see --csv)")

    if detections:
        occupancy = {}
        for det in detections:
            occupancy.setdefault(det["channel"], []).append(det)

        print(f"\n{len(occupancy)} channel(s) active:")
        for channel in sorted(occupancy, key=lambda c: -len(occupancy[c]))[:20]:
            hits = occupancy[channel]
            airtime = sum(d["duration_ms"] for d in hits)
            duty = airtime / (times[-1] * 1000) * 100
            print(f"  ch{channel:4d}  {len(hits):4d} burst(s)  "
                  f"{airtime:9.1f} ms airtime  {duty:6.3f}% duty")

        # Per-channel duty cycle is the regulatory constraint: HKCA 1078 allows
        # 0.4 s in any 4 s window (10%), against 0.4 s in 20 s (2%) under FCC
        # 15.247. Flag anything that would breach the tighter US figure, since
        # an FCC-variant waveform is the likely thing under test.
        for channel, hits in occupancy.items():
            airtime = sum(d["duration_ms"] for d in hits)
            duty = airtime / (times[-1] * 1000) * 100
            if duty > 2.0:
                print(f"\nNOTE: ch{channel} duty {duty:.2f}% exceeds the FCC 15.247 "
                      f"figure of 2% (0.4 s/20 s).\n      HKCA 1078 permits 10% "
                      f"(0.4 s/4 s), so this may still be compliant in HK.")
                break

    if args.hop_report and len(detections) > 1:
        print("\nhop sequence (first 60 visits):")
        sequence = [d["channel"] for d in detections]
        print("  " + " ".join(str(c) for c in sequence[:60]))

        revisits = {}
        for i, det in enumerate(detections):
            for later in detections[i + 1:]:
                if later["channel"] == det["channel"]:
                    revisits.setdefault(det["channel"], []).append(
                        later["time_s"] - det["time_s"])
                    break

        if revisits:
            intervals = [v for values in revisits.values() for v in values]
            print(f"\nrevisit interval: min {min(intervals):.2f}s  "
                  f"median {np.median(intervals):.2f}s  max {max(intervals):.2f}s")
            print(f"unique channels visited: {len(set(sequence))}")
            print("\nTo test whether the hop list is a seeded PRNG or time-derived,\n"
                  "capture again after a power cycle and compare the two sequences.")

    if args.csv:
        with open(args.csv, "w") as handle:
            handle.write("time_s,channel,freq_hz,power_db,duration_ms\n")
            for det in detections:
                handle.write(f"{det['time_s']:.6f},{det['channel']},{det['freq_hz']:.0f},"
                             f"{det['power_db']:.2f},{det['duration_ms']:.2f}\n")
        print(f"\nwrote {args.csv} ({len(detections)} rows)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
