"""IQ file reading and minimal DSP helpers.

numpy-only by design. scipy is a common thing to be missing on a machine that
has been locked into a screened enclosure, so everything needed here is
implemented against numpy alone.

Supported sample formats
------------------------
    cs8   int8   interleaved I,Q            (HackRF, most SDR tooling)
    cu8   uint8  interleaved I,Q, offset 127 (RTL-SDR native)
    cs16  int16  interleaved I,Q            (USRP, PortaPack .C16 captures)
    cf32  float32 interleaved I,Q           (GNU Radio default)

A SigMF pair (`foo.sigmf-data` + `foo.sigmf-meta`) is detected automatically
and the format/sample-rate/frequency are read from the metadata.
"""

import json
import os

import numpy as np

FORMATS = {
    "cs8": (np.int8, 2, 127.0, 0.0),
    "cu8": (np.uint8, 2, 127.5, -127.5),
    "cs16": (np.int16, 2, 32767.0, 0.0),
    "cf32": (np.float32, 2, 1.0, 0.0),
}

# SigMF datatype string -> our format key.
SIGMF_DATATYPES = {
    "ci8": "cs8",
    "ci8_le": "cs8",
    "cu8": "cu8",
    "cu8_le": "cu8",
    "ci16_le": "cs16",
    "cf32_le": "cf32",
}


class Capture:
    """A loaded IQ capture plus whatever metadata we could establish."""

    def __init__(self, samples, sample_rate, center_freq=None, path=None):
        self.samples = samples
        self.sample_rate = float(sample_rate)
        self.center_freq = center_freq
        self.path = path

    @property
    def duration(self):
        return len(self.samples) / self.sample_rate

    def __repr__(self):
        cf = "unknown" if self.center_freq is None else f"{self.center_freq/1e6:.4f} MHz"
        return (
            f"<Capture {len(self.samples)} samples, "
            f"{self.sample_rate/1e3:.1f} ksps, centre {cf}, {self.duration:.2f} s>"
        )


def _sigmf_meta_path(path):
    """Return the sigmf-meta path partnering `path`, or None."""
    if path.endswith(".sigmf-data"):
        meta = path[: -len(".sigmf-data")] + ".sigmf-meta"
        if os.path.exists(meta):
            return meta
    meta = path + ".sigmf-meta"
    return meta if os.path.exists(meta) else None


def read_sigmf_meta(path):
    """Extract (format, sample_rate, center_freq) from a SigMF metadata file."""
    with open(path) as handle:
        meta = json.load(handle)

    global_meta = meta.get("global", {})
    fmt = SIGMF_DATATYPES.get(global_meta.get("core:datatype", ""))
    rate = global_meta.get("core:sample_rate")

    freq = None
    captures = meta.get("captures", [])
    if captures:
        freq = captures[0].get("core:frequency")

    return fmt, rate, freq


def load(path, fmt=None, sample_rate=None, center_freq=None, count=None, offset=0):
    """Load an IQ capture as a complex64 array.

    `count` and `offset` are in samples (not bytes) and let you page through a
    capture too large to hold in memory.
    """
    meta_path = _sigmf_meta_path(path)
    if meta_path:
        meta_fmt, meta_rate, meta_freq = read_sigmf_meta(meta_path)
        fmt = fmt or meta_fmt
        sample_rate = sample_rate or meta_rate
        center_freq = center_freq if center_freq is not None else meta_freq

    if fmt is None:
        fmt = _guess_format(path)
    if fmt not in FORMATS:
        raise ValueError(f"unknown sample format {fmt!r}; expected one of {sorted(FORMATS)}")
    if sample_rate is None:
        raise ValueError("sample_rate is required (no SigMF metadata found)")

    dtype, per_sample, scale, bias = FORMATS[fmt]
    itemsize = np.dtype(dtype).itemsize

    raw = np.fromfile(
        path,
        dtype=dtype,
        count=-1 if count is None else count * per_sample,
        offset=offset * per_sample * itemsize,
    )

    # Drop a trailing half-sample from a truncated capture rather than erroring.
    if len(raw) % 2:
        raw = raw[:-1]

    raw = raw.astype(np.float32)
    if bias:
        raw += bias
    if scale != 1.0:
        raw /= scale

    samples = raw[0::2] + 1j * raw[1::2]
    return Capture(samples.astype(np.complex64), sample_rate, center_freq, path)


def _guess_format(path):
    """Infer a sample format from the file extension. Defaults to cs16."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    aliases = {
        "cs8": "cs8", "sc8": "cs8", "c8": "cs8", "iq8": "cs8",
        "cu8": "cu8", "u8": "cu8",
        "cs16": "cs16", "sc16": "cs16", "c16": "cs16", "iq16": "cs16",
        "cf32": "cf32", "fc32": "cf32", "f32": "cf32", "complex": "cf32",
    }
    return aliases.get(ext, "cs16")


def write_cs16(path, samples, sample_rate=None, center_freq=None):
    """Write complex samples as interleaved int16, with a SigMF sidecar."""
    peak = np.max(np.abs(samples)) or 1.0
    scaled = (samples / peak * 32000).astype(np.complex64)

    interleaved = np.empty(len(scaled) * 2, dtype=np.int16)
    interleaved[0::2] = np.real(scaled).astype(np.int16)
    interleaved[1::2] = np.imag(scaled).astype(np.int16)
    interleaved.tofile(path)

    if sample_rate:
        meta = {
            "global": {
                "core:datatype": "ci16_le",
                "core:sample_rate": float(sample_rate),
                "core:description": "UNB FSK toolkit capture",
            },
            "captures": [{"core:sample_start": 0}],
            "annotations": [],
        }
        if center_freq:
            meta["captures"][0]["core:frequency"] = float(center_freq)
        with open(path + ".sigmf-meta", "w") as handle:
            json.dump(meta, handle, indent=2)


# --------------------------------------------------------------------------
# Minimal DSP, numpy only
# --------------------------------------------------------------------------

def lowpass_taps(cutoff_hz, sample_rate, num_taps=127):
    """Windowed-sinc lowpass. Odd tap count gives a linear, integral delay."""
    if num_taps % 2 == 0:
        num_taps += 1

    fc = cutoff_hz / sample_rate  # cycles/sample
    n = np.arange(num_taps) - (num_taps - 1) / 2
    taps = 2 * fc * np.sinc(2 * fc * n)
    taps *= np.hamming(num_taps)
    return (taps / np.sum(taps)).astype(np.float32)


def fir_filter(samples, taps):
    """FFT-based 'same' convolution. Much faster than np.convolve on long
    captures, and the only filter we need."""
    n = len(samples) + len(taps) - 1
    fft_size = 1 << int(np.ceil(np.log2(n)))

    spectrum = np.fft.fft(samples, fft_size) * np.fft.fft(taps, fft_size)
    filtered = np.fft.ifft(spectrum)

    start = (len(taps) - 1) // 2
    return filtered[start:start + len(samples)].astype(np.complex64)


def lowpass_real(signal, cutoff_hz, sample_rate, num_taps=127):
    """Lowpass a real-valued signal (i.e. a demodulated frequency track).

    Filtering after quadrature demodulation is not optional. The per-sample
    instantaneous frequency estimate is extremely noisy — at 48 samples per
    symbol, raw sign changes occur almost every sample and any zero-crossing
    measurement returns the sample rate rather than the symbol rate.
    """
    taps = lowpass_taps(cutoff_hz, sample_rate, num_taps)
    filtered = fir_filter(signal.astype(np.complex64), taps)
    return np.real(filtered).astype(np.float32)


def frequency_shift(samples, shift_hz, sample_rate):
    """Mix by -shift_hz, bringing that frequency to DC."""
    t = np.arange(len(samples), dtype=np.float64) / sample_rate
    lo = np.exp(-2j * np.pi * shift_hz * t).astype(np.complex64)
    return samples * lo


def decimate(samples, factor, sample_rate, cutoff_ratio=0.45):
    """Filter then downsample. Returns (samples, new_rate)."""
    if factor <= 1:
        return samples, sample_rate

    cutoff = cutoff_ratio * sample_rate / factor
    filtered = fir_filter(samples, lowpass_taps(cutoff, sample_rate))
    return filtered[::factor], sample_rate / factor


def quadrature_demod(samples, sample_rate):
    """Instantaneous frequency in Hz, one sample shorter than the input.

    This is the correct way to measure a low-modulation-index FSK signal. A
    spectrogram cannot do it: resolving 2 ms symbols needs a ~0.5 ms window,
    which gives ~2 kHz resolution — far too coarse to see a shift that may be
    as small as 125 Hz.
    """
    products = samples[1:] * np.conj(samples[:-1])
    return (np.angle(products) * sample_rate / (2 * np.pi)).astype(np.float32)


def magnitude_db(samples, floor_db=-140.0):
    mag = np.abs(samples).astype(np.float64)
    return np.maximum(20 * np.log10(mag + 1e-12), floor_db)
