#!/usr/bin/env python3
"""Generate synthetic UNB 2-FSK captures to validate the analysis chain.

Run this BEFORE you trust any result from unb_demod.py on real data. It
produces a signal whose parameters you already know, so if the demodulator
cannot recover them, the problem is in the tooling or your invocation — not in
the signal you are chasing. On site you will not be able to ask anyone, so
being able to separate "my script is broken" from "the signal isn't what I
expected" is worth the two minutes.

The waveform matches what the PortaPack UNB FSK TX app emits, including the
details that bite:

  * Bit order is MSB-first within each byte, matching proc_fsk.cpp's
    `(data[bit_pos >> 3] << (bit_pos & 7)) & 0x80`.
  * A '1' bit is +deviation, a '0' bit is -deviation.
  * proc_fsk transmits 32 bits past the end of the frame; the app zero-pads
    them, so the burst ends with 32 zero bits (a -deviation tone).

Examples
--------
    # Default: 500 bps, 125 Hz deviation, matches the app's defaults
    ./unb_selftest.py --out selftest.cs16

    # A hard case: low SNR and a clock error like an uncorrected TCXO
    ./unb_selftest.py --out hard.cs16 --snr 3 --freq-offset 900

    # Multi-burst hopping file for testing unb_survey.py
    ./unb_selftest.py --out hop.cs16 --bursts 20 --hop --sample-rate 250000
"""

import argparse
import sys

import numpy as np

import iqio


def frame_bits(preamble_bytes, sync_word, payload, tail_bits=32):
    """Build the app's frame as an MSB-first bit array."""
    data = bytearray()
    data.extend([0x55] * preamble_bytes)
    data.append((sync_word >> 8) & 0xFF)
    data.append(sync_word & 0xFF)
    data.extend(payload)

    bits = np.unpackbits(np.frombuffer(bytes(data), dtype=np.uint8))
    return np.concatenate([bits, np.zeros(tail_bits, dtype=np.uint8)])


def modulate(bits, sample_rate, symbol_rate, deviation, freq_offset=0.0):
    """Continuous-phase 2-FSK. Phase continuity matters: a discontinuous
    modulator produces spectral splatter that a real radio would not."""
    samples_per_symbol = sample_rate / symbol_rate
    total = int(round(len(bits) * samples_per_symbol))

    symbol_index = np.minimum((np.arange(total) / samples_per_symbol).astype(int), len(bits) - 1)
    inst_freq = np.where(bits[symbol_index] > 0, deviation, -deviation) + freq_offset

    phase = 2 * np.pi * np.cumsum(inst_freq) / sample_rate
    return np.exp(1j * phase).astype(np.complex64)


def noise_power_for(snr_db, signal_power=1.0):
    """Noise power giving the requested SNR against a unit-amplitude carrier."""
    return signal_power / (10 ** (snr_db / 10))


def add_noise(signal, noise_power):
    """Add complex AWGN of a given absolute power.

    Power is passed in rather than derived from the signal, so that the gaps
    between bursts get the *same* noise floor as the bursts. Deriving it from
    the signal would give a silent gap zero noise, which makes burst detection
    look far better than it will be on real data.
    """
    noise = np.sqrt(noise_power / 2) * (
        np.random.randn(len(signal)) + 1j * np.random.randn(len(signal))
    )
    return (signal + noise).astype(np.complex64)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="output IQ file (cs16 + SigMF sidecar)")
    parser.add_argument("--sample-rate", type=float, default=48000, help="output sample rate (Hz)")
    parser.add_argument("--symbol-rate", type=float, default=500, help="symbol rate (bps)")
    parser.add_argument("--deviation", type=float, default=125, help="FSK deviation (Hz, peak)")
    parser.add_argument("--freq-offset", type=float, default=0.0,
                        help="carrier offset (Hz), e.g. to emulate an uncorrected clock")
    parser.add_argument("--snr", type=float, default=20, help="SNR in dB")
    parser.add_argument("--preamble", type=int, default=8, help="preamble length in bytes of 0x55")
    parser.add_argument("--sync", default="2DD4", help="sync word, hex")
    parser.add_argument("--payload", default="0123456789ABCDEF", help="payload, hex")
    parser.add_argument("--bursts", type=int, default=1, help="number of bursts")
    parser.add_argument("--gap", type=float, default=0.5, help="gap between bursts (s)")
    parser.add_argument("--pad", type=float, default=0.2,
                        help="noise-only lead-in/lead-out (s), so a noise floor exists")
    parser.add_argument("--hop", action="store_true",
                        help="place each burst on a different 25 kHz channel offset")
    parser.add_argument("--seed", type=int, default=1, help="RNG seed for reproducibility")
    args = parser.parse_args()

    np.random.seed(args.seed)

    payload = bytes.fromhex(args.payload)
    sync = int(args.sync, 16)
    bits = frame_bits(args.preamble, sync, payload)

    burst_duration = len(bits) / args.symbol_rate
    print(f"frame       : {len(bits)} bits ({len(bits)-32} + 32 tail)")
    print(f"burst        : {burst_duration*1000:.1f} ms at {args.symbol_rate:g} bps")
    print(f"deviation    : {args.deviation:g} Hz  (modulation index "
          f"{2*args.deviation/args.symbol_rate:.2f})")

    if args.hop and args.sample_rate < 100000:
        print("\nWARNING: --hop places channels on a 25 kHz grid; a sample rate below "
              "100 kHz cannot represent them. Raise --sample-rate.", file=sys.stderr)

    gap_samples = int(args.gap * args.sample_rate)
    pad_samples = int(args.pad * args.sample_rate)

    # The modulator emits a unit-amplitude carrier, so one noise power serves
    # both the bursts and the gaps between them - giving a consistent floor.
    noise_power = noise_power_for(args.snr)

    def idle(length):
        return add_noise(np.zeros(length, dtype=np.complex64), noise_power)

    # Lead-in noise, so burst detection has an idle region to measure a noise
    # floor against. A capture that is wall-to-wall signal has no floor to find.
    pieces = []
    if pad_samples:
        pieces.append(idle(pad_samples))

    for index in range(args.bursts):
        offset = args.freq_offset
        if args.hop:
            # Channels either side of centre, within the captured bandwidth.
            span = int(args.sample_rate / 2 / 25000)
            if span > 0:
                offset += 25000 * (((index * 7) % (2 * span)) - span)

        burst = modulate(bits, args.sample_rate, args.symbol_rate, args.deviation, offset)
        pieces.append(add_noise(burst, noise_power))

        if index != args.bursts - 1:
            pieces.append(idle(gap_samples))

    if pad_samples:
        pieces.append(idle(pad_samples))

    signal = np.concatenate(pieces)
    iqio.write_cs16(args.out, signal, args.sample_rate, center_freq=920012500)

    print(f"\nwrote {args.out}: {len(signal)} samples, "
          f"{len(signal)/args.sample_rate:.2f} s at {args.sample_rate/1e3:g} ksps")
    print(f"\nNow verify the chain recovers what you just set:")
    print(f"  ./unb_demod.py {args.out} --expect-rate {args.symbol_rate:g} "
          f"--expect-deviation {args.deviation:g}")


if __name__ == "__main__":
    main()
