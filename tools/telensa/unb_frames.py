#!/usr/bin/env python3
"""Frame-structure analysis across many bursts: alignment, entropy, CRC search.

This is the tool that turns a pile of demodulated bursts into a frame layout.
The method is per-bit-position entropy across an aligned collection:

  * A position that never changes is a protocol constant — preamble, sync word,
    a version field, a fixed length.
  * A position constant *within* one device but different between devices is
    addressing. This is why the capture plan says two telecells differing only
    in serial number, captured back to back: without that contrast, addressing
    and protocol constants are indistinguishable.
  * A position that varies freely is payload, counter, or CRC.
  * Uniformly high entropy everywhere after the sync word means whitening or
    encryption. Before concluding it is crypto, test common LFSR whitening —
    a de-whitened stream shows structure immediately.

Input is the output of `unb_demod.py --bits-out`: one burst per line as a string
of 0/1. Lines may be prefixed `label:` to group bursts by device, which is what
enables the addressing analysis.

Examples
--------
    ./unb_frames.py bursts.txt --sync 2DD4
    ./unb_frames.py bursts.txt --sync 2DD4 --crc-search

    # With device labels, to separate addressing from protocol constants
    #   cell_A:0101...
    #   cell_B:0101...
    ./unb_frames.py labelled.txt --sync 2DD4
"""

import argparse
import sys
from collections import Counter, defaultdict

import numpy as np

# (name, polynomial, init, reflect_in, reflect_out, xor_out)
CRC16_VARIANTS = [
    ("CRC-16/CCITT-FALSE", 0x1021, 0xFFFF, False, False, 0x0000),
    ("CRC-16/XMODEM", 0x1021, 0x0000, False, False, 0x0000),
    ("CRC-16/KERMIT", 0x1021, 0x0000, True, True, 0x0000),
    ("CRC-16/X-25", 0x1021, 0xFFFF, True, True, 0xFFFF),
    ("CRC-16/MCRF4XX", 0x1021, 0xFFFF, True, True, 0x0000),
    ("CRC-16/ARC", 0x8005, 0x0000, True, True, 0x0000),
    ("CRC-16/MODBUS", 0x8005, 0xFFFF, True, True, 0x0000),
    ("CRC-16/USB", 0x8005, 0xFFFF, True, True, 0xFFFF),
    ("CRC-16/DNP", 0x3D65, 0x0000, True, True, 0xFFFF),
    ("CRC-16/MAXIM", 0x8005, 0x0000, True, True, 0xFFFF),
]


def reflect(value, width):
    result = 0
    for _ in range(width):
        result = (result << 1) | (value & 1)
        value >>= 1
    return result


def crc16(data, poly, init, reflect_in, reflect_out, xor_out):
    crc = init
    for byte in data:
        if reflect_in:
            byte = reflect(byte, 8)
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    if reflect_out:
        crc = reflect(crc, 16)
    return crc ^ xor_out


def load_bursts(path):
    """Read the bit file. Returns [(label, np.array of bits), ...]."""
    bursts = []
    with open(path) as handle:
        for lineno, line in enumerate(handle, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            label = None
            if ":" in line:
                label, _, line = line.partition(":")
                label = label.strip()
                line = line.strip()

            if not set(line) <= {"0", "1"}:
                print(f"warning: line {lineno} has non-binary characters, skipping",
                      file=sys.stderr)
                continue

            bursts.append((label, np.array([int(c) for c in line], dtype=np.uint8)))
    return bursts


def bits_from_hex(text):
    value = int(text, 16)
    width = len(text) * 4
    return np.array([(value >> i) & 1 for i in range(width - 1, -1, -1)], dtype=np.uint8)


def find_pattern(bits, pattern):
    if len(bits) < len(pattern):
        return -1
    windows = np.lib.stride_tricks.sliding_window_view(bits, len(pattern))
    matches = np.flatnonzero(np.all(windows == pattern, axis=1))
    return int(matches[0]) if len(matches) else -1


def align(bursts, sync_bits, drop_sync):
    """Align bursts so position 0 is the same place in every frame.

    Without alignment the entropy analysis is meaningless: a one-bit timing
    difference between captures smears every field across two positions.
    """
    aligned, skipped = [], 0

    for label, bits in bursts:
        if sync_bits is None:
            aligned.append((label, bits))
            continue

        at = find_pattern(bits, sync_bits)
        if at < 0:
            skipped += 1
            continue

        start = at + (len(sync_bits) if drop_sync else 0)
        aligned.append((label, bits[start:]))

    return aligned, skipped


def entropy_map(bursts):
    """Per-position ones-fraction and Shannon entropy across bursts."""
    length = min(len(bits) for _, bits in bursts)
    matrix = np.vstack([bits[:length] for _, bits in bursts])

    ones = matrix.mean(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        entropy = -(ones * np.log2(ones) + (1 - ones) * np.log2(1 - ones))
    entropy = np.nan_to_num(entropy)

    return matrix, ones, entropy


def classify(ones, entropy, high_threshold=0.75):
    """One character per bit position, for a visual field map."""
    glyphs = []
    for fraction, h in zip(ones, entropy):
        if h == 0:
            glyphs.append("#" if fraction > 0.5 else ".")
        elif h < 0.25:
            glyphs.append("l")
        elif h < high_threshold:
            glyphs.append("m")
        else:
            glyphs.append("?")
    return "".join(glyphs)


def print_map(glyphs, width=64):
    print("  legend: . const-0   # const-1   l low-entropy   "
          "m mid-entropy   ? high-entropy\n")
    for start in range(0, len(glyphs), width):
        print(f"  {start:5d}  {glyphs[start:start+width]}")


def device_analysis(bursts, matrix, entropy):
    """Positions constant within a device but differing between devices."""
    groups = defaultdict(list)
    for index, (label, _) in enumerate(bursts):
        if label:
            groups[label].append(index)

    if len(groups) < 2:
        return None

    per_device_constant = np.ones(matrix.shape[1], dtype=bool)
    device_values = {}

    for label, indices in groups.items():
        subset = matrix[indices]
        constant = np.all(subset == subset[0], axis=0)
        per_device_constant &= constant
        device_values[label] = subset[0]

    labels = sorted(groups)
    differs = np.zeros(matrix.shape[1], dtype=bool)
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            differs |= device_values[labels[i]] != device_values[labels[j]]

    return {
        "groups": {label: len(idx) for label, idx in groups.items()},
        "address_candidates": np.flatnonzero(per_device_constant & differs),
        "protocol_constants": np.flatnonzero(per_device_constant & ~differs & (entropy == 0)),
    }


def describe_runs(positions, kind):
    """Collapse a position list into contiguous runs for readability."""
    if len(positions) == 0:
        print(f"  no {kind} found")
        return

    runs, start, previous = [], positions[0], positions[0]
    for position in positions[1:]:
        if position != previous + 1:
            runs.append((start, previous))
            start = position
        previous = position
    runs.append((start, previous))

    text = ", ".join(
        f"{a}" if a == b else f"{a}-{b} ({b-a+1} bits)" for a, b in runs
    )
    print(f"  {kind}: {text}")


def crc_search(bursts, crc_width=16, max_candidates=6):
    """Look for a trailing CRC over a byte-aligned span of each frame.

    Requires every frame to validate under the same variant, which makes a
    false positive very unlikely with three or more frames.
    """
    usable = [bits for _, bits in bursts if len(bits) >= crc_width + 16]
    if len(usable) < 2:
        print("  need at least 2 frames of sufficient length")
        return

    length = min(len(bits) for bits in usable)
    frames = [bits[:length] for bits in usable]
    print(f"  {len(frames)} frames, {length} bits each")

    found = 0
    # Sweep where the CRC sits and where the covered data starts. Both are
    # byte-aligned; a bit-aligned CRC is possible but rare enough to skip.
    for crc_end in range(length, max(length - 24, crc_width) - 1, -8):
        crc_start = crc_end - crc_width
        if crc_start <= 0 or crc_start % 8:
            continue

        for data_start in range(0, min(crc_start, 96), 8):
            data_bits = crc_start - data_start
            if data_bits < 8 or data_bits % 8:
                continue

            for name, poly, init, ref_in, ref_out, xor_out in CRC16_VARIANTS:
                if all(
                    crc16(np.packbits(bits[data_start:crc_start]).tobytes(),
                          poly, init, ref_in, ref_out, xor_out)
                    == int("".join(str(b) for b in bits[crc_start:crc_end]), 2)
                    for bits in frames
                ):
                    print(f"  MATCH {name}: data bits {data_start}-{crc_start-1}, "
                          f"CRC at {crc_start}-{crc_end-1}")
                    found += 1
                    if found >= max_candidates:
                        return

    if not found:
        print("  no CRC-16 match. The checksum may be a different width, cover a\n"
              "  non-byte-aligned span, sit somewhere other than the tail, or the\n"
              "  frame may be whitened — de-whiten before searching again.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bits", help="bit file from unb_demod.py --bits-out")
    parser.add_argument("--sync", help="sync word (hex) to align on")
    parser.add_argument("--drop-sync", action="store_true",
                        help="start position 0 after the sync word rather than at it")
    parser.add_argument("--crc-search", action="store_true", help="hunt for a trailing CRC-16")
    parser.add_argument("--width", type=int, default=64, help="field map width")
    args = parser.parse_args()

    bursts = load_bursts(args.bits)
    if not bursts:
        print("no usable bursts in input", file=sys.stderr)
        return 1

    print(f"loaded {len(bursts)} burst(s), "
          f"lengths {min(len(b) for _, b in bursts)}-{max(len(b) for _, b in bursts)} bits")

    sync_bits = bits_from_hex(args.sync) if args.sync else None
    bursts, skipped = align(bursts, sync_bits, args.drop_sync)

    if sync_bits is not None:
        print(f"aligned on sync {args.sync.upper()}; {skipped} burst(s) lacked it")
        if not bursts:
            print("\nNo burst contained the sync word. Either the alignment pattern is\n"
                  "wrong, or the frames are not what you think. Run without --sync to\n"
                  "look at raw entropy first.", file=sys.stderr)
            return 1

    if len(bursts) < 2:
        print("\nOnly one burst — entropy analysis needs a collection to compare.\n"
              "Capture more bursts; the field map below is meaningless with n=1.",
              file=sys.stderr)
        return 1

    matrix, ones, entropy = entropy_map(bursts)
    print(f"comparing {matrix.shape[0]} bursts over {matrix.shape[1]} common bit positions\n")

    print_map(classify(ones, entropy), args.width)

    constant = np.flatnonzero(entropy == 0)
    high = np.flatnonzero(entropy >= 0.75)

    print(f"\nstructure:")
    describe_runs(constant, "constant")
    describe_runs(high, "high-entropy")

    mean_entropy = float(np.mean(entropy))
    print(f"\n  mean entropy {mean_entropy:.3f} bits/position")
    if mean_entropy > 0.9 and len(constant) == 0:
        print("  Everything is high entropy with no constants at all. That is the\n"
              "  signature of whitening or encryption — or of misalignment. Rule out\n"
              "  misalignment first: without a correct sync anchor every position\n"
              "  looks random.")

    analysis = device_analysis(bursts, matrix, entropy)
    if analysis:
        print(f"\ndevice grouping: "
              f"{', '.join(f'{k}={v}' for k, v in sorted(analysis['groups'].items()))}")
        describe_runs(analysis["address_candidates"], "address candidates")
        describe_runs(analysis["protocol_constants"], "shared constants")
    else:
        print("\nNo device labels found. Prefix lines with 'label:' to separate\n"
              "addressing from protocol constants — that contrast is the only way\n"
              "to tell them apart.")

    if args.crc_search:
        print("\nCRC search:")
        crc_search(bursts)

    return 0


if __name__ == "__main__":
    sys.exit(main())
