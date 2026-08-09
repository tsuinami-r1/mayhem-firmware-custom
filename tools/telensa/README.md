# UNB FSK measurement toolkit

Capture and analysis tooling for ultra-narrowband 2-FSK links, built around the
publicly confirmed physical layer of the Telensa PLANet street-lighting system.
Companion to the `UNB FSK TX` PortaPack app in
`firmware/application/external/telensa_tx/`.

**Written to be used offline.** If you are reading this in a screened enclosure
with no way to ask a question, everything you need should be here. Section 8
lists the things that are genuinely unknown, so you can tell a gap in the
tooling from a gap in the public record.

---

## 1. Scope — read this first

The physical layer is public. The protocol is not.

**Confirmed** (FCC ID XYD-2N4D test report, Telensa BS4 manual, telecell
datasheet): FSK, 500 bps, 25 kHz channel raster, FHSS, ~400 ms bursts,
399.25 ms measured per-channel occupancy in a 20 s window, telecell 25–100 mW
ERP, basestation 4 W EIRP / −139 dBm sensitivity, telecell −124 dBm sensitivity.

**Not published, by Telensa or anyone else:**

- FSK deviation, modulation index, filtering
- Frame structure — preamble, sync word, addressing, CRC, FEC, whitening
- Hop sequence generation and synchronisation
- Link-layer security and key management
- The Asia / "S-variant" operating band and channel plan

Two consequences. First, the transmitter app is a **signal generator**, not a
PLANet protocol implementation — it cannot key a telecell, and its framing is a
deliberately generic placeholder. Second, the 920–925 MHz channel plan used
throughout is **inferred** from Hong Kong spectrum regulation (HKCA 1049/1078,
Cap. 106Z), not from a vendor statement. Treat it as a hypothesis to test, and
override it with `--base` / `--channels` if you learn better.

The ~200-bit frame budget quoted in the source document is dwell × rate — an
upper bound, not an observed frame size.

## 2. Install

```sh
python3 -m pip install -r requirements.txt   # numpy only
```

`scipy` is deliberately **not** required. Everything needed — windowed-sinc
filtering, FFT convolution, Welch spectra, quadrature demodulation — is
implemented against numpy in `iqio.py`, because a missing dependency is not a
problem you can fix from inside a shielded room.

## 3. Pre-flight: validate the chain before you trust it

Do this **before** connecting to anything, and again after any change to the
capture setup. It costs two minutes and it is the difference between "the signal
isn't what I expected" and "my tooling is broken" — a distinction you cannot
resolve by asking someone once you are on site.

```sh
./unb_selftest.py --out selftest.cs16
./unb_demod.py selftest.cs16 --expect-rate 500 --expect-deviation 125
```

Expect two `[PASS]` lines. The synthetic signal matches the PortaPack app's
output exactly, including the awkward details: MSB-first bit order within each
byte, `1` = +deviation, and the 32 trailing zero bits that `proc_fsk` clocks out
past the end of the frame.

Harder cases worth running once, so you recognise the failure modes:

```sh
# Low SNR and an uncorrected-clock frequency error. Note --symbol-rate-max:
# narrowing it towards the true rate is what makes weak signals work.
./unb_selftest.py --out hard.cs16 --snr 10 --freq-offset 900
./unb_demod.py hard.cs16 --symbol-rate-max 1000 \
    --expect-rate 500 --expect-deviation 125

# Where the deviation estimate finally breaks down (expect a FAIL)
./unb_selftest.py --out worse.cs16 --snr 6 --freq-offset 900
./unb_demod.py worse.cs16 --symbol-rate-max 1000 --expect-deviation 125

# High modulation index, the easy case
./unb_selftest.py --out h4.cs16 --deviation 1000
./unb_demod.py h4.cs16 --expect-rate 500 --expect-deviation 1000

# Multi-burst hopping file, for the survey tool
./unb_selftest.py --out hop.cs16 --bursts 12 --hop --sample-rate 250000
./unb_survey.py hop.cs16 --center 920012500 --threshold 8 --hop-report
```

## 4. The thing most likely to ruin the campaign: clock stability

The deviation is unpublished, and the plausible range spans an order of
magnitude. Two readings of the same evidence:

- Carson's rule against "occupied bandwidth of a few kHz" → Δf ≈ 1 kHz, h ≈ 4.
- The −139 dBm basestation sensitivity at ~8 dB SNR implies a receive filter
  near the symbol rate, which implies **h ≈ 0.5, Δf ≈ 125 Hz**.

The second is the self-consistent reading, and it is what comparable UNB systems
do — Sigfox RC4, sharing 920–925 MHz, runs 100 bps in ~100 Hz.

If Δf really is ~125 Hz, then at 920 MHz **a 1 ppm clock error is 920 Hz — seven
times the deviation.** Your frequency error would completely swamp the
modulation. A standard SDR TCXO is not adequate.

**A GPSDO or OCXO 10 MHz reference is mandatory, not a refinement.** A Leo
Bodnar mini GPSDO into the HackRF's CLKIN, or a USRP with the GPSDO option, gets
you to ~1 ppb. Budget for this before anything else.

Second consequence: **do not try to read deviation off a spectrogram.** The
time–bandwidth product defeats you — resolving 2 ms symbols needs a ~0.5 ms
window, giving ~2 kHz resolution, far too coarse to see a 125 Hz shift. These
tools use coherent quadrature demodulation, which works at any modulation index.

## 5. Equipment

| Item | Recommendation | Why |
|---|---|---|
| Reference | **GPSDO, 10 MHz** | Non-negotiable, per §4 |
| SDR (characterisation) | USRP B210, Airspy R2, or HackRF + CLKIN | Must accept an external clock |
| SDR (hop mapping) | Anything covering 5 MHz in one shot, ≥8 Msps | Stepped sweeps miss a sparse hopper |
| Front end | 902–928 or 920–925 MHz BPF | Mobile downlink at 925–960 MHz sits 5 MHz away at basestation power |
| Attenuation | 30–40 dB step attenuator | A 4 W basestation in a screened enclosure will destroy a front end — do the level budget before connecting |
| Antennas | Two | Separating uplink from downlink by position/polarisation; they are 16 dB apart in power |

An RTL-SDR v4 is usable for single-channel work once you know where to look, but
it cannot cover 5 MHz and its 1 ppm TCXO is marginal. Not a primary instrument.

Do not use the PortaPack for characterisation — 8-bit ADC and a modest clock. It
is the transmitter here, not the analyser.

## 6. Capture campaigns

Traffic is sparse by design: telecells hold their schedules locally and report
rarely, so waiting is the slow path. In a cage you can **stimulate** instead,
which is the whole advantage of having the hardware:

- **Power-cycle a telecell.** Association and commissioning traffic is the
  densest and most structured you will see, and where addressing is most likely
  to appear in the clear.
- **Occlude the light sensor** to force a dusk/dawn switching transition.
- **Force faults** — open the lamp circuit, pull the load — to trigger fault
  reporting.
- **NFC provisioning.** Documented as a feature; what it exchanges is not.
  Capture the RF side during and just after provisioning.
- **Vary one thing at a time, and log it.** Two telecells differing only in
  serial number, captured back to back, is what makes §7's addressing analysis
  possible. Without that contrast, addressing and protocol constants are
  indistinguishable.

Keep a common time reference between your stimulus log and your captures.

### Campaign 1 — survey (hours)

Full 5 MHz, ~8–10 Msps. Confirms which band and variant is live and gives burst
timing statistics. Do **not** record raw IQ: 10 Msps/cs8 is 20 MB/s, 72 GB/hour,
~1.7 TB/day. Run the detector and keep IQ only around detections.

### Campaign 2 — single-channel deep capture (the important one)

Park on a channel the survey found. **250 ksps, 16-bit, GPSDO locked.** Yields
deviation, exact symbol rate, burst envelope, preamble. If you run only one
campaign, run this one — it is what unblocks calibrating the generator and
everything downstream.

Aim for **≥15 dB SNR**. See §8 for why that number, not a smaller one.

### Campaign 3 — hop mapping (long)

Wideband, detector log only, over many hours. Yields the `(time, channel)`
sequence. 15.247 requires a pseudo-random list with roughly equal average
channel use, so look for LFSR-like structure — and **capture again after a power
cycle**, because whether the sequence repeats distinguishes a seeded PRNG from
one derived from time or node identity.

## 7. Analysis workflow

```sh
# 1. Which channels are busy, when, in what order
./unb_survey.py wide.cs16 --sample-rate 10000000 --center 922500000 \
    --band hk --csv detections.csv --hop-report

# 2. Measure the physical layer on a single channel
./unb_demod.py deep.sigmf-data --symbol-rate-max 1000 \
    --bits-out bursts.txt --json-out bursts.json

# 3. Pull one channel out of a wideband capture instead
./unb_demod.py wide.cs16 --sample-rate 2000000 --channel-offset -75000

# 4. Frame structure across many bursts
./unb_frames.py bursts.txt --sync <found-sync> --drop-sync --crc-search
```

For step 4, label lines by device to separate addressing from protocol
constants — `unb_demod.py` writes one burst per line, so prefix them:

```
cellA:010101...
cellB:010101...
```

`unb_frames.py` prints a per-position field map:

```
. const-0   # const-1   l low-entropy   m mid-entropy   ? high-entropy
```

Constant runs are protocol constants. Positions constant within a device but
differing between devices are address candidates. Uniformly high entropy with no
constants anywhere means whitening, encryption — **or misalignment**. Rule out
misalignment first: without a correct sync anchor, every position looks random.

`--crc-search` tries ten common CRC-16 variants over byte-aligned spans and
requires every frame to validate under the same one, so a false positive is
unlikely with three or more frames.

Interactive alternatives worth having on the machine: **Universal Radio Hacker**
(built for exactly this diffing work) and **inspectrum** (for eyeballing bursts).
Both beat writing it from scratch.

## 8. Known limits, measured

Measured by sweeping synthetic signals at 500 bps, h = 0.5, run with
`--symbol-rate-max 1000`. Results are the same with and without a 900 Hz carrier
offset, so the figures below hold regardless of clock error within the AFC range.

| Input SNR | Deviation estimate | Symbol rate estimate |
|---|---|---|
| ≥ 20 dB | < 1% error | < 0.1% error |
| 15 dB | ~1.4% error | < 0.1% error |
| 10–12 dB | ~2–3% error | < 0.1% error |
| 8 dB | ~3.4% error | ~0.1% error |
| 6 dB | **~20% error** | ~0.15% error |

**SNR here is measured across the full capture bandwidth** (48 kHz in the
selftest), not in the signal's own bandwidth. That is the pessimistic
convention: "6 dB" leaves plenty of in-band SNR once the IF filter has narrowed
to 2.5 kHz, which is why the symbol rate survives so far down. Do not read these
as in-band figures.

The two parameters fail differently and independently. Symbol rate is a timing
measurement and, once the burst is centred and filtered, is remarkably robust.
Deviation is an amplitude-domain measurement and degrades steadily, falling off a
cliff below ~8 dB. So a burst can legitimately give a trustworthy rate and a
useless deviation, or the reverse.

**Aim for ≥15 dB SNR.** In a cage with the hardware this is easy and it puts you
clear of every cliff above.

`unb_demod.py` gates the symbol rate on two signals: an intrinsic interval-fit
quality (do the transition intervals fit integer multiples of one period?) and,
when available, agreement with the independent spectral estimate. It prints
`[UNRELIABLE]` when those fail. The spectral estimate can be legitimately absent
— a signal with no alternating preamble will not produce one — and that alone
does not invalidate the timing measurement.

Three settings drive weak-signal performance:

- `--afc-range` — how far off centre to search for each burst's carrier,
  applied **per burst** so it works with hopping. Must cover your worst-case
  clock error (1 ppm at 920 MHz is 920 Hz) but stay under half the channel
  spacing so it cannot lock onto the neighbour. Without AFC, an offset carrier
  lands in the IF filter's transition band and the asymmetric attenuation
  compresses the measured deviation — a systematic error worth ~7% at 900 Hz,
  and total signal loss by 3 kHz.
- `--if-bandwidth` — applied to the complex signal **after** AFC centring and
  **before** demodulation. FM demodulation has a threshold effect: below roughly
  10 dB in-band SNR the output is click-dominated in a way no post-detection
  filtering recovers.
- `--symbol-rate-max` — sets the filter ladder that finds the preamble line, and
  the auto IF bandwidth. Lowering it towards the true rate is the single most
  effective thing you can do for a weak slow signal.

If the defaults find nothing, narrow these before concluding there is no signal.

### What these tools cannot tell you

- Whether a recovered frame is *semantically* valid. There is no reference to
  check against.
- Anything about key management or the provisioning trust model.
- Whether the S-variant band assumption is right. Energy in 920–925 MHz is
  consistent with an S-variant *or* with Sigfox RC4 *or* with UHF RFID — burst
  length and hop behaviour are the discriminators, not band occupancy.

## 9. Transmitter app

`UNB FSK TX`, in the PortaPack TX menu. Emits 2-FSK with configurable band and
channel, deviation, symbol rate, preamble length, sync word and payload, in
single or continuous mode with fixed, sequential or pseudo-random hopping.

Its purpose in this campaign is to be a **known** signal: transmit a waveform
whose parameters you set, confirm the receive chain recovers them, then trust the
chain on unknown signals. The generator and the measurement plan bootstrap each
other — that is why §3 comes before §6.

Defaults are 920.0125 MHz (HK channel 0), 125 Hz deviation, 500 bps, 8 bytes of
0x55 preamble, sync 0x2DD4. The deviation default is the §4 inference and the
sync word is a conventional placeholder; **change both** once you have measured
the real thing.

Frame layout is `[0x55 × n][sync hi][sync lo][payload]`, MSB-first, with 32 zero
bits of tail. `telensa.hpp` documents the provenance of every constant and which
ones are inferences rather than facts.

## 10. Files

| File | Purpose |
|---|---|
| `iqio.py` | IQ loading (cs8/cu8/cs16/cf32, SigMF) and numpy-only DSP |
| `unb_selftest.py` | Synthetic signal generator for chain validation |
| `unb_demod.py` | Burst detection, deviation, symbol rate, bit recovery |
| `unb_survey.py` | Channel occupancy and hop-sequence logging |
| `unb_frames.py` | Multi-burst alignment, entropy analysis, CRC search |

Capture metadata: prefer SigMF, so parameters cannot get separated from the
data. Failing that, a sidecar recording centre frequency, sample rate, gain,
antenna, timestamp, reference lock status, and **what you stimulated**. That
last field is the one people omit and later wish they had not.
