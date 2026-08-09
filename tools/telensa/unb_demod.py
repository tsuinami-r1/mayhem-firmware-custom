#!/usr/bin/env python3
"""Measure UNB 2-FSK bursts: deviation, symbol rate, timing, and bits.

This is the tool that answers the two questions the public record does not:
what is the FSK deviation, and what is the exact symbol rate. Everything else
it produces — burst timing, recovered bits — feeds unb_frames.py.

Method
------
Quadrature demodulation, not spectrogram analysis. If the deviation really is
~125 Hz (modulation index ~0.5), a spectrogram cannot resolve it: seeing 2 ms
symbols needs a ~0.5 ms window, which gives ~2 kHz frequency resolution. The
instantaneous-frequency approach works at any modulation index.

Deviation and carrier offset come from a two-level split of the demodulated
signal: the midpoint between the levels is the carrier offset, half their
separation is the deviation. Symbol rate comes from the intervals between
zero crossings — the shortest recurring interval is one symbol period —
refined by a least-squares fit against integer symbol counts.

Examples
--------
    # Validate against a known synthetic signal first
    ./unb_selftest.py --out selftest.cs16
    ./unb_demod.py selftest.cs16 --expect-rate 500 --expect-deviation 125

    # A real single-channel capture
    ./unb_demod.py capture.sigmf-data --bits-out bursts.txt

    # Pull one channel out of a wideband capture
    ./unb_demod.py wide.cs16 --sample-rate 2000000 --channel-offset -75000
"""

import argparse
import json
import sys

import numpy as np

import iqio


def detect_bursts(samples, sample_rate, threshold_db=10.0, min_duration_ms=20.0,
                  smooth_ms=2.0):
    """Find bursts by magnitude envelope. Returns [(start, end), ...] in samples.

    The threshold is relative to the median magnitude, which is a decent noise
    floor estimate as long as the capture is mostly idle — which, for a system
    that reports as sparsely as this one, it will be.
    """
    mag_db = iqio.magnitude_db(samples)

    smooth_samples = max(1, int(smooth_ms * sample_rate / 1000))
    kernel = np.ones(smooth_samples) / smooth_samples
    smoothed = np.convolve(mag_db, kernel, mode="same")

    noise_floor = np.median(smoothed)
    above = smoothed > (noise_floor + threshold_db)

    # Contiguous True runs.
    edges = np.diff(above.astype(np.int8))
    starts = list(np.flatnonzero(edges == 1) + 1)
    ends = list(np.flatnonzero(edges == -1) + 1)

    if above[0]:
        starts.insert(0, 0)
    if above[-1]:
        ends.append(len(above))

    min_samples = int(min_duration_ms * sample_rate / 1000)
    return [(s, e) for s, e in zip(starts, ends) if (e - s) >= min_samples], noise_floor


def estimate_levels(demod, iterations=8):
    """Two-level split of the demodulated signal.

    Returns (offset, deviation): the carrier offset is the midpoint of the two
    levels, the deviation is half their separation. Iterating the split makes
    it robust to an unbalanced bit distribution, which matters because a frame
    is not guaranteed to have equal numbers of ones and zeros.
    """
    threshold = np.median(demod)

    for _ in range(iterations):
        high = demod[demod > threshold]
        low = demod[demod <= threshold]

        if len(high) == 0 or len(low) == 0:
            return float(np.mean(demod)), 0.0

        high_level = np.median(high)
        low_level = np.median(low)
        new_threshold = (high_level + low_level) / 2

        if np.isclose(new_threshold, threshold):
            break
        threshold = new_threshold

    return float((high_level + low_level) / 2), float((high_level - low_level) / 2)


def estimate_carrier_offset(samples, sample_rate, search_bw):
    """Power-weighted spectral centroid: where the burst's carrier actually sits.

    This is automatic frequency control, and it is not optional here. A 2-FSK
    signal offset from DC lands in the IF filter's transition band, where the
    +deviation tone is attenuated more than the -deviation tone. That asymmetry
    compresses the measured deviation — a systematic error, independent of SNR,
    worth ~7% at 900 Hz offset and total signal loss by 3 kHz.

    And 900 Hz is not a pathological figure: at 920 MHz it is what a 1 ppm
    reference gives you. Centring the burst before filtering removes the whole
    class of error.

    A centroid rather than a peak, because at low modulation index the spectrum
    has two lobes and the carrier sits between them.
    """
    window = np.hanning(len(samples))
    spectrum = np.abs(np.fft.fftshift(np.fft.fft(samples * window))) ** 2
    freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 1 / sample_rate))

    band = np.abs(freqs) <= search_bw / 2
    if not np.any(band):
        return 0.0

    freqs, spectrum = freqs[band], spectrum[band]

    # Weight only bins that clearly carry signal, or the centroid is dragged
    # towards DC by the noise floor spread across the whole search band.
    threshold = np.median(spectrum) * 8
    significant = spectrum > threshold
    if not np.any(significant):
        return 0.0

    weights = spectrum[significant]
    return float(np.sum(freqs[significant] * weights) / np.sum(weights))


def welch_spectrum(signal, sample_rate, segments=8):
    """Segment-averaged magnitude spectrum. Returns (freqs, magnitudes).

    Averaging trades frequency resolution for variance, which is the right
    trade when hunting a preamble line in a noisy burst: a single FFT of a
    low-SNR signal has enough variance that noise peaks rival the real line.
    """
    if len(signal) < 64:
        return None, None

    seg_len = max(64, len(signal) // segments)
    seg_len = min(seg_len, len(signal))
    window = np.hanning(seg_len)

    accumulator = None
    count = 0
    for start in range(0, len(signal) - seg_len + 1, max(1, seg_len // 2)):
        chunk = signal[start:start + seg_len] * window
        power = np.abs(np.fft.rfft(chunk)) ** 2
        accumulator = power if accumulator is None else accumulator + power
        count += 1

    if not count:
        return None, None

    return np.fft.rfftfreq(seg_len, 1 / sample_rate), np.sqrt(accumulator / count)


def coarse_symbol_rate(raw_demod, sample_rate, max_rate):
    """Rough symbol rate from the spectrum of the demodulated signal.

    An alternating preamble (0x55...) demodulates to a square wave at half the
    symbol rate, producing a strong spectral line. Nearly every FSK system uses
    an alternating preamble for exactly this reason — it is what the receiver's
    own clock recovery locks to.

    The difficulty is that measuring the line needs a filter narrow enough to
    see it above the noise, and choosing that filter needs the answer. So we
    sweep a ladder of cutoffs and keep whichever produces the most prominent
    line. A cutoff below Rb/2 destroys the line and scores badly; one far above
    it buries the line in noise and also scores badly. The best score sits near
    the true rate.

    Returns (rate, cutoff, prominence) or (None, None, 0).
    """
    best = (None, None, 0.0)

    cutoff = max_rate
    while cutoff >= max(20.0, max_rate / 64):
        if cutoff < sample_rate / 2.5:
            filtered = iqio.lowpass_real(raw_demod, cutoff, sample_rate)
            freqs, magnitudes = welch_spectrum(filtered - np.mean(filtered), sample_rate)

            if freqs is not None:
                # The line sits at Rb/2, and must be inside the filter passband.
                band = (freqs > 1.0) & (freqs <= min(cutoff, max_rate) / 2)
                if np.any(band):
                    values = magnitudes[band]
                    peak_index = int(np.argmax(values))

                    # Exclude the peak and its skirts from the floor estimate.
                    # A narrow search band holds few bins, most of them belonging
                    # to the line itself, so a plain median measures the signal
                    # rather than the noise under it and prominence collapses.
                    guard = max(2, len(values) // 16)
                    mask = np.ones(len(values), dtype=bool)
                    mask[max(0, peak_index - guard):peak_index + guard + 1] = False

                    floor = np.median(values[mask]) if np.any(mask) else np.median(values)
                    prominence = float(values[peak_index] / floor) if floor > 0 else 0.0

                    if prominence > best[2]:
                        best = (2 * float(freqs[band][peak_index]), cutoff, prominence)

        cutoff /= 2

    # A prominence below this is indistinguishable from a noise peak.
    if best[2] < 5.0:
        return None, None, best[2]

    return best


def estimate_symbol_period(demod, offset, sample_rate):
    """Symbol period in samples, from zero-crossing intervals.

    Every interval between transitions is an integer number of symbols, so the
    shortest recurring interval is one symbol. We take a robust low percentile
    as a first estimate, then refine by fitting all intervals to integer
    multiples of it.
    """
    centred = demod - offset
    signs = np.sign(centred)
    signs[signs == 0] = 1

    crossings = np.flatnonzero(np.diff(signs) != 0)
    if len(crossings) < 4:
        return None, 0, 0.0

    intervals = np.diff(crossings).astype(np.float64)
    intervals = intervals[intervals > 0]
    if len(intervals) < 3:
        return None, 0, 0.0

    # Cluster of shortest intervals: one symbol each.
    cutoff = np.percentile(intervals, 25)
    short = intervals[intervals <= max(cutoff, np.min(intervals) * 1.5)]
    estimate = float(np.median(short)) if len(short) else float(np.min(intervals))

    if estimate <= 0:
        return None, 0, 0.0

    # Refine: every interval should be an integer number of symbols. Fit by
    # least squares against the rounded counts, discarding poor matches.
    counts = np.round(intervals / estimate)
    valid = counts >= 1
    counts, kept = counts[valid], intervals[valid]

    if len(kept) < 3:
        return estimate, len(crossings), 0.0

    residual = np.abs(kept - counts * estimate) / estimate
    good = residual < 0.25
    if np.count_nonzero(good) >= 3:
        estimate = float(np.sum(counts[good] * kept[good]) / np.sum(counts[good] ** 2))

        # Re-score against the refined estimate.
        counts = np.round(kept / estimate)
        residual = np.abs(kept - counts * estimate) / estimate
        good = residual < 0.25

    # Fit quality is an independent self-check: if the transition intervals
    # really are integer multiples of one period, the signal is a clean NRZ
    # stream at that rate. Noise-driven crossings do not fit a common period,
    # so this collapses exactly when the estimate becomes untrustworthy — and
    # it does not depend on the spectral method, which can fail for unrelated
    # reasons (no alternating preamble, for instance).
    quality = float(np.count_nonzero(good) / len(kept))

    return estimate, len(crossings), quality


def recover_bits(demod, offset, symbol_period):
    """Slice the demodulated signal into bits.

    Timing recovery is a phase sweep: sample on a symbol-spaced grid at every
    candidate phase and keep the one where the samples land furthest from the
    decision threshold — i.e. in the centre of the eye.
    """
    if symbol_period is None or symbol_period < 2:
        return np.array([], dtype=np.uint8), 0.0

    centred = demod - offset
    num_symbols = int(len(centred) / symbol_period)
    if num_symbols < 1:
        return np.array([], dtype=np.uint8), 0.0

    best_phase, best_score = 0.0, -1.0
    for phase in np.linspace(0, symbol_period, 16, endpoint=False):
        idx = (phase + np.arange(num_symbols) * symbol_period).astype(int)
        idx = idx[idx < len(centred)]
        score = float(np.mean(np.abs(centred[idx])))
        if score > best_score:
            best_phase, best_score = phase, score

    idx = (best_phase + np.arange(num_symbols) * symbol_period).astype(int)
    idx = idx[idx < len(centred)]

    return (centred[idx] > 0).astype(np.uint8), best_phase


def bits_to_hex(bits):
    """Pack MSB-first, matching proc_fsk's bit order."""
    padded = np.concatenate([bits, np.zeros((-len(bits)) % 8, dtype=np.uint8)])
    return np.packbits(padded).tobytes().hex().upper()


def find_pattern(bits, pattern_bits):
    """Index of the first occurrence of a bit pattern, or -1."""
    if len(pattern_bits) == 0 or len(bits) < len(pattern_bits):
        return -1

    windows = np.lib.stride_tricks.sliding_window_view(bits, len(pattern_bits))
    matches = np.flatnonzero(np.all(windows == pattern_bits, axis=1))
    return int(matches[0]) if len(matches) else -1


def analyse_burst(samples, sample_rate, index, args):
    """Measure one burst. Returns a result dict."""
    # AFC first, per burst: with frequency hopping, successive bursts sit at
    # different offsets, so this cannot be done once globally.
    afc = estimate_carrier_offset(samples, sample_rate, args.afc_range)
    if afc:
        samples = iqio.frequency_shift(samples, afc, sample_rate)

    # Now the burst is centred, the IF filter is symmetric about it. Filtering
    # before demodulation is what gets a weak burst above the FM threshold,
    # below which the demod output is click-dominated beyond recovery.
    if args.if_bandwidth and args.if_bandwidth < sample_rate / 2.5:
        samples = iqio.fir_filter(
            samples, iqio.lowpass_taps(args.if_bandwidth / 2, sample_rate)
        )

    demod = iqio.quadrature_demod(samples, sample_rate)

    # Trim the edges: filter transients and rise/fall corrupt the first and
    # last symbols and would bias the level estimate.
    trim = min(len(demod) // 20, int(0.005 * sample_rate))
    raw = demod[trim:len(demod) - trim] if len(demod) > 4 * trim else demod

    # Sweep filter widths to find the preamble line, then re-filter just above
    # the estimated rate. That final narrowing is where the sensitivity comes
    # from: a filter 8x wider than necessary keeps 8x the noise.
    estimate, _, prominence = coarse_symbol_rate(raw, sample_rate, args.symbol_rate_max)

    if estimate:
        narrow_cutoff = min(1.5 * estimate, sample_rate / 2.5)
    else:
        narrow_cutoff = min(args.symbol_rate_max, sample_rate / 2.5)

    core = iqio.lowpass_real(raw, narrow_cutoff, sample_rate)

    offset, deviation = estimate_levels(core)
    symbol_period, crossings, fit_quality = estimate_symbol_period(core, offset, sample_rate)

    symbol_rate = sample_rate / symbol_period if symbol_period else None
    bits, _ = recover_bits(core, offset, symbol_period)

    result = {
        "burst": index,
        "duration_ms": len(samples) / sample_rate * 1000,
        # Report the true offset from the capture centre: what AFC removed plus
        # whatever residual the level estimate found.
        "carrier_offset_hz": afc + offset,
        "afc_shift_hz": afc,
        "deviation_hz": deviation,
        "symbol_rate_bps": symbol_rate,
        "modulation_index": (2 * deviation / symbol_rate) if symbol_rate else None,
        "transitions": crossings,
        "bit_count": int(len(bits)),
        "bits_hex": bits_to_hex(bits),
        "coarse_rate_bps": estimate,
        "preamble_line_prominence": prominence,
        "demod_bandwidth_hz": narrow_cutoff,
    }

    # Two independent quality signals gate the symbol rate.
    #
    # The interval fit quality is primary: it is intrinsic to the zero-crossing
    # measurement and does not assume the signal has an alternating preamble.
    # The spectral estimate is used as a corroborating cross-check *when it is
    # available* — it can legitimately be absent (no alternating preamble, or a
    # search band too narrow to establish prominence) without implying the
    # timing measurement is wrong.
    #
    # Empirically the zero-crossing refinement holds to well under 1% down to
    # about 12 dB SNR and collapses below roughly 8 dB, while the deviation
    # estimate — a robust median, not a timing measurement — stays good to a few
    # percent even at 6 dB. So a burst can legitimately yield a trustworthy
    # deviation and a worthless symbol rate.
    reliable = symbol_rate is not None and fit_quality >= 0.8
    result["rate_fit_quality"] = fit_quality

    if reliable and estimate is not None:
        disagreement = abs(symbol_rate - estimate) / estimate
        result["rate_disagreement"] = disagreement
        reliable = disagreement < 0.25

    result["rate_reliable"] = bool(reliable)

    # Look for the conventional markers. Absence is informative too: no 0x55
    # run means the preamble is something else, which is worth knowing early.
    preamble = np.array([0, 1] * 16, dtype=np.uint8)
    result["preamble_at"] = find_pattern(bits, preamble)

    if args.sync:
        sync_value = int(args.sync, 16)
        sync_bits = np.array(
            [(sync_value >> i) & 1 for i in range(len(args.sync) * 4 - 1, -1, -1)],
            dtype=np.uint8,
        )
        result["sync_at"] = find_pattern(bits, sync_bits)

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("capture", help="IQ capture file")
    parser.add_argument("--format", help="cs8 / cu8 / cs16 / cf32 (default: from SigMF or extension)")
    parser.add_argument("--sample-rate", type=float, help="sample rate (Hz), if no SigMF metadata")
    parser.add_argument("--channel-offset", type=float, default=0.0,
                        help="shift this offset (Hz) to DC before demodulating")
    parser.add_argument("--decimate", type=int, default=0,
                        help="decimation factor (0 = choose automatically)")
    parser.add_argument("--threshold", type=float, default=10.0,
                        help="burst detection threshold above noise floor (dB)")
    parser.add_argument("--min-duration", type=float, default=20.0,
                        help="ignore bursts shorter than this (ms)")
    parser.add_argument("--sync", default="2DD4", help="sync word to search for (hex, '' to skip)")
    parser.add_argument("--bits-out", help="write recovered bits here, one burst per line")
    parser.add_argument("--json-out", help="write full results as JSON")
    parser.add_argument("--expect-rate", type=float, help="expected symbol rate, for self-test")
    parser.add_argument("--expect-deviation", type=float, help="expected deviation, for self-test")
    parser.add_argument("--max-bursts", type=int, default=0, help="stop after N bursts (0 = all)")
    parser.add_argument("--whole-file", action="store_true",
                        help="skip burst detection; treat the whole capture as one burst")
    parser.add_argument("--symbol-rate-max", type=float, default=4000.0,
                        help="upper bound on plausible symbol rate (Hz). Sets the demod "
                             "filter ladder; raise it if the signal is faster than "
                             "expected, lower it to dig a weak slow signal out of noise")
    parser.add_argument("--if-bandwidth", type=float, default=0.0,
                        help="IF filter bandwidth (Hz) applied per burst after AFC "
                             "centring. 0 = auto (2.5x symbol-rate-max). THE key setting "
                             "for weak signals: too wide and FM threshold effect destroys "
                             "the burst, too narrow and the modulation is clipped")
    parser.add_argument("--afc-range", type=float, default=6000.0,
                        help="how far off centre (Hz) to search for each burst's carrier. "
                             "Must cover your worst-case clock error - 1 ppm at 920 MHz "
                             "is 920 Hz - but stay under half the channel spacing so it "
                             "cannot lock onto the neighbouring channel")
    parser.add_argument("--detect-bandwidth", type=float, default=0.0,
                        help="burst-detection filter width (Hz). 0 = auto "
                             "(if-bandwidth + 2x afc-range)")
    args = parser.parse_args()

    capture = iqio.load(args.capture, fmt=args.format, sample_rate=args.sample_rate)
    print(f"loaded {capture}")

    if not args.if_bandwidth:
        # 2.5x the maximum symbol rate comfortably passes an FSK signal at that
        # rate for any sane modulation index, without opening up needlessly.
        args.if_bandwidth = 2.5 * args.symbol_rate_max
    print(f"IF bandwidth {args.if_bandwidth/1e3:.2f} kHz, "
          f"AFC range +/-{args.afc_range/1e3:.2f} kHz, "
          f"symbol rate ceiling {args.symbol_rate_max:g} bps")

    samples = capture.samples
    rate = capture.sample_rate

    if args.channel_offset:
        samples = iqio.frequency_shift(samples, args.channel_offset, rate)
        print(f"shifted {args.channel_offset:+g} Hz to DC")

    # Decimate hard. At 500 bps with sub-kHz deviation everything of interest
    # lives in a few kHz, and narrowing the bandwidth is free SNR.
    factor = args.decimate
    if factor == 0:
        factor = max(1, int(rate / 20000))
    if factor > 1:
        samples, rate = iqio.decimate(samples, factor, rate)
        print(f"decimated by {factor} to {rate/1e3:.1f} ksps")

    # Burst detection gets its own, wider filter; per-burst analysis works from
    # the unfiltered samples so it can centre each burst before narrowing.
    #
    # Detection needs *a* filter because it is a magnitude test and inherits the
    # noise in whatever bandwidth it is handed: a burst 15 dB up in its own
    # bandwidth may be only 3 dB up across the whole capture, and be missed. But
    # it must stay wide enough not to reject a burst that is merely off
    # frequency, which is why it is not the same filter the analysis uses.
    detect_bw = args.detect_bandwidth or (args.if_bandwidth + 2 * args.afc_range)

    if detect_bw < rate / 2.5:
        detect_samples = iqio.fir_filter(samples, iqio.lowpass_taps(detect_bw / 2, rate))
        print(f"detection filter {detect_bw/1e3:.2f} kHz")
    else:
        detect_samples = samples

    bursts, noise_floor = detect_bursts(detect_samples, rate, args.threshold, args.min_duration)
    print(f"noise floor {noise_floor:.1f} dB, {len(bursts)} burst(s) detected\n")

    if not bursts and args.whole_file:
        bursts = [(0, len(samples))]
        print("no bursts detected; --whole-file given, treating the capture as one burst\n")
    elif not bursts:
        # A capture that is wall-to-wall signal has no idle region, so the
        # median-based floor sits *on* the burst and nothing clears it. That is
        # a likely shape for a hand-trimmed single-burst file, so fall back
        # rather than failing — but say so, because the alternative cause is a
        # capture with no signal in it at all.
        span = np.percentile(iqio.magnitude_db(detect_samples), [10, 90])
        if (span[1] - span[0]) < args.threshold:
            print(f"no distinct bursts (magnitude spread {span[1]-span[0]:.1f} dB is under "
                  f"the {args.threshold:.0f} dB threshold).\n"
                  "Treating the whole capture as a single burst — correct for a pre-trimmed\n"
                  "file, wrong if the capture is pure noise. Check the deviation below is\n"
                  "plausible rather than random.\n")
            bursts = [(0, len(samples))]
        else:
            print("No bursts found. Things to try, in order of likelihood:\n"
                  "  - lower --threshold (a weak burst may be only a few dB up)\n"
                  "  - lower --min-duration if the bursts are shorter than expected\n"
                  "  - check --channel-offset: the signal may not be at DC\n"
                  "  - confirm --sample-rate is right; a wrong rate breaks everything\n"
                  "  - pass --whole-file to force analysis of a pre-trimmed capture",
                  file=sys.stderr)
            return 1

    if args.max_bursts:
        bursts = bursts[:args.max_bursts]

    results = []
    for index, (start, end) in enumerate(bursts):
        result = analyse_burst(samples[start:end], rate, index, args)
        result["start_s"] = start / rate
        results.append(result)

        rate_str = f"{result['symbol_rate_bps']:.2f} bps" if result["symbol_rate_bps"] else "unknown"
        if not result["rate_reliable"]:
            rate_str += "  [UNRELIABLE]"
        h_str = f"{result['modulation_index']:.2f}" if result["modulation_index"] else "?"

        print(f"burst {index:3d}  t={result['start_s']:8.3f}s  {result['duration_ms']:7.1f} ms")
        print(f"            deviation  {result['deviation_hz']:8.1f} Hz    (h = {h_str})")
        print(f"            offset     {result['carrier_offset_hz']:+8.1f} Hz")
        print(f"            symbol rate {rate_str}")
        print(f"            bits       {result['bit_count']}"
              f"   preamble@{result['preamble_at']}"
              f"   sync@{result.get('sync_at', 'n/a')}")
        print(f"            {result['bits_hex'][:64]}"
              f"{'...' if len(result['bits_hex']) > 64 else ''}\n")

    # Aggregate across bursts: the spread tells you how much to trust it. Only
    # bursts that passed the cross-check contribute to the symbol rate.
    deviations = [r["deviation_hz"] for r in results]
    rates = [r["symbol_rate_bps"] for r in results if r["rate_reliable"]]
    unreliable = sum(1 for r in results if not r["rate_reliable"])

    print("=" * 62)
    print(f"deviation    mean {np.mean(deviations):8.1f} Hz   sd {np.std(deviations):6.1f} Hz"
          f"   (n={len(deviations)})")
    if rates:
        print(f"symbol rate  mean {np.mean(rates):8.2f} bps  sd {np.std(rates):6.2f} bps"
              f"   (n={len(rates)})")
    else:
        print("symbol rate  no reliable estimate")

    if unreliable:
        print(f"\n{unreliable} of {len(results)} burst(s) gave an unreliable symbol rate.\n"
              "The timing estimate needs roughly 12 dB SNR; the deviation figure above is\n"
              "still usable at much lower SNR. To improve it: narrow --if-bandwidth and\n"
              "--symbol-rate-max towards the true values, or get a stronger capture.")

    exit_code = 0
    if args.expect_rate and rates:
        error = abs(np.mean(rates) - args.expect_rate) / args.expect_rate * 100
        status = "PASS" if error < 2.0 else "FAIL"
        print(f"\n[{status}] symbol rate: expected {args.expect_rate:g}, "
              f"got {np.mean(rates):.2f} ({error:.2f}% error)")
        exit_code |= 0 if status == "PASS" else 1

    if args.expect_deviation:
        error = abs(np.mean(deviations) - args.expect_deviation) / args.expect_deviation * 100
        status = "PASS" if error < 10.0 else "FAIL"
        print(f"[{status}] deviation:   expected {args.expect_deviation:g}, "
              f"got {np.mean(deviations):.1f} ({error:.2f}% error)")
        exit_code |= 0 if status == "PASS" else 1

    if args.bits_out:
        with open(args.bits_out, "w") as handle:
            for result in results:
                handle.write("".join(str(b) for b in
                                     np.unpackbits(np.frombuffer(
                                         bytes.fromhex(result["bits_hex"]), dtype=np.uint8
                                     ))[:result["bit_count"]]) + "\n")
        print(f"\nwrote {args.bits_out} ({len(results)} bursts)")

    if args.json_out:
        with open(args.json_out, "w") as handle:
            json.dump(results, handle, indent=2)
        print(f"wrote {args.json_out}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
