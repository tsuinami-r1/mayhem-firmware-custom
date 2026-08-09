#!/usr/bin/env python3
"""Generate the UNB FSK measurement field manual as a PDF.

Kept in the repo so the manual can be regenerated when procedures or firmware
line references change - a field manual that drifts out of step with the code is
worse than none. Run after any change to the placeholder values in telensa.hpp.

    python3 make_field_manual.py --out UNB_FSK_Field_Manual.pdf
"""

import argparse
import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)

INK = colors.HexColor("#1a1a1a")
ACCENT = colors.HexColor("#1f4e79")
WARN = colors.HexColor("#8b2500")
RULE = colors.HexColor("#b0b0b0")
SHADE = colors.HexColor("#eef2f6")
BOXBG = colors.HexColor("#fbf7ec")


def build_styles():
    styles = getSampleStyleSheet()
    base = dict(fontName="Helvetica", textColor=INK, leading=12.5)

    styles.add(ParagraphStyle("Cover", fontName="Helvetica-Bold", fontSize=23,
                              leading=27, textColor=ACCENT, alignment=TA_CENTER,
                              spaceAfter=6))
    styles.add(ParagraphStyle("CoverSub", fontName="Helvetica", fontSize=11.5,
                              leading=16, textColor=INK, alignment=TA_CENTER))
    styles.add(ParagraphStyle("H1", fontName="Helvetica-Bold", fontSize=15,
                              leading=18, textColor=ACCENT, spaceBefore=16,
                              spaceAfter=7))
    styles.add(ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=11.5,
                              leading=14, textColor=INK, spaceBefore=11,
                              spaceAfter=4))
    styles.add(ParagraphStyle("H3", fontName="Helvetica-BoldOblique", fontSize=10,
                              leading=13, textColor=INK, spaceBefore=8, spaceAfter=3))
    styles.add(ParagraphStyle("Body", fontSize=9.6, spaceAfter=5, **base))
    styles.add(ParagraphStyle("Bul", fontSize=9.6, leftIndent=11,
                              bulletIndent=2, spaceAfter=2.5, **base))
    styles.add(ParagraphStyle("Step", fontSize=9.6, leftIndent=15,
                              bulletIndent=2, spaceAfter=4, **base))
    styles.add(ParagraphStyle("Cmd", fontName="Courier-Bold", fontSize=8.4,
                              leading=11.2, textColor=colors.HexColor("#08240b"),
                              leftIndent=8, spaceBefore=3, spaceAfter=4))
    styles.add(ParagraphStyle("Cell", fontSize=8.5, leading=10.8,
                              fontName="Helvetica", textColor=INK))
    styles.add(ParagraphStyle("CellB", fontSize=8.5, leading=10.8,
                              fontName="Helvetica-Bold", textColor=INK))
    styles.add(ParagraphStyle("CellM", fontSize=7.9, leading=10.2,
                              fontName="Courier", textColor=INK))
    styles.add(ParagraphStyle("Warn", fontSize=9.6, leading=12.5,
                              fontName="Helvetica", textColor=WARN))
    styles.add(ParagraphStyle("Foot", fontSize=8, leading=10,
                              fontName="Helvetica-Oblique",
                              textColor=colors.HexColor("#555555")))
    return styles


S = build_styles()


def P(text, style="Body"):
    return Paragraph(text, S[style])


def bullets(items, style="Bul"):
    return [Paragraph(t, S[style], bulletText="-") for t in items]


def steps(items):
    return [Paragraph(t, S["Step"], bulletText=f"{i}.")
            for i, t in enumerate(items, 1)]


def cmd(*lines):
    return Paragraph("<br/>".join(lines), S["Cmd"])


def table(rows, widths, header=True, mono_cols=()):
    data = []
    for r_i, row in enumerate(rows):
        out = []
        for c_i, cell in enumerate(row):
            if isinstance(cell, Paragraph):
                out.append(cell)
            else:
                if r_i == 0 and header:
                    style = "CellB"
                elif c_i in mono_cols:
                    style = "CellM"
                else:
                    style = "Cell"
                out.append(Paragraph(str(cell), S[style]))
        data.append(out)

    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), SHADE)]
    t.setStyle(TableStyle(style))
    return t


def callout(title, body, bg=BOXBG, border=WARN):
    inner = [P(f"<b>{title}</b>", "Warn"), P(body, "Body")]
    t = Table([[inner]], colWidths=[168 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.9, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def blank_rows(headers, widths, count):
    rows = [headers] + [[""] * len(headers) for _ in range(count)]
    t = table(rows, widths)
    t.setStyle(TableStyle([("ROWBACKGROUNDS", (0, 1), (-1, -1),
                           [colors.white, colors.HexColor("#f7f7f7")]),
                           ("MINROWHEIGHTS", (0, 1), (-1, -1), 15)]))
    return t


# ---------------------------------------------------------------------------
# Measurement procedure content
# ---------------------------------------------------------------------------

MEASUREMENTS = [
    {
        "id": "M1",
        "title": "Band, channel raster and channel-0 offset",
        "pins": "band_defs[] base frequency and channel count "
                "(telensa.cpp:33/37/40); UNB_CHANNEL_SPACING (telensa.hpp:67)",
        "why": "The 920-925 MHz Asia plan is an inference from Hong Kong regulation, "
               "not a vendor statement. Nothing else in the manual is safe to trust "
               "until you know which band is actually live and where its channels sit.",
        "setup": [
            "Wideband SDR, 8-10 Msps, GPSDO locked.",
            "Band-pass filter ahead of the LNA. Attenuate per section 1.3.",
            "Antenna positioned for the basestation first - it is 16 dB stronger "
            "than a telecell and far easier to find.",
        ],
        "procedure": [
            "Record 60 s centred on 922.5 MHz at 10 Msps. This covers 920-925 in "
            "one shot; do not use stepped sweeps, they will miss a sparse hopper.",
            "Run the survey against the inferred HK plan.",
            "Repeat centred on 915.0 MHz and on 869.5 MHz to rule the other two "
            "variants in or out.",
            "For whichever band shows energy, note the exact centre frequency of "
            "several detections from the CSV.",
            "Compute the spacing between adjacent occupied channel centres, and "
            "the offset of the lowest one from the round band edge.",
        ],
        "commands": [
            "./unb_survey.py wide_922M5.cs16 --sample-rate 10000000 \\",
            "    --center 922500000 --band hk --csv m1_hk.csv --hop-report",
        ],
        "expect": "Detections roughly 400 ms long on a 25 kHz grid. If the raster is "
                  "25 kHz and channel 0 sits 12.5 kHz inside the band edge, the "
                  "firmware defaults are correct as they stand.",
        "accept": [
            "At least 20 detections, on at least 6 distinct channels.",
            "Adjacent occupied centres differ by a consistent value within +/-500 Hz. "
            "That value is the raster.",
            "The channel-0 offset is consistent across at least 3 separate captures.",
        ],
        "fail": [
            "<b>No energy in any band.</b> Confirm the system is powered and "
            "transmitting - stimulate it per section 1.5 rather than waiting.",
            "<b>Energy present but not on a 25 kHz grid.</b> Do not force the grid. "
            "Record the actual centres and re-derive the raster with --band custom.",
            "<b>Energy in 920-925 but bursts far shorter than 400 ms.</b> Likely "
            "Sigfox RC4 or UHF RFID, not PLANet. Burst length and hop behaviour are "
            "the discriminators, not band occupancy.",
        ],
    },
    {
        "id": "M2",
        "title": "Burst envelope, dwell and cadence",
        "pins": "Confirms the 399.25 ms figure from the FCC test report and "
                "establishes the inter-burst interval, which sets the "
                "continuous-mode cadence discussed in section 5.",
        "why": "Burst length times symbol rate bounds the frame size. It is also "
               "the cheapest sanity check that you are looking at the right system.",
        "setup": [
            "Single channel identified by M1. 250 ksps, 16-bit, GPSDO locked.",
            "Aim for at least 15 dB SNR - see section 1.3.",
        ],
        "procedure": [
            "Park on the busiest channel from the M1 CSV and record 10 minutes.",
            "Run the demodulator and read the per-burst duration column.",
            "Record the gap between consecutive burst start times.",
            "Repeat on a second channel to confirm the figures are not "
            "channel-specific.",
        ],
        "commands": [
            "./unb_demod.py ch_deep.sigmf-data --symbol-rate-max 1000 \\",
            "    --json-out m2_bursts.json",
        ],
        "expect": "Burst durations clustered near 400 ms. Inter-burst gaps will be "
                  "long and irregular: telecells hold their schedules locally and "
                  "report sparsely.",
        "accept": [
            "At least 30 bursts measured.",
            "Duration standard deviation under 5 percent of the mean.",
            "Mean duration recorded to the nearest millisecond.",
        ],
        "fail": [
            "<b>Durations wildly inconsistent.</b> Your detection threshold is "
            "probably clipping burst edges. Lower --threshold and re-run.",
            "<b>Almost no bursts in 10 minutes.</b> Expected. Stimulate the system "
            "(section 1.5) instead of extending the wait.",
        ],
    },
    {
        "id": "M3",
        "title": "FSK deviation and modulation index",
        "pins": "UNB_DEFAULT_DEVIATION (telensa.hpp:73)",
        "why": "This is the single largest gap in the public record and the headline "
               "target of the campaign. The FCC report states \"FSK 500 bps\" and "
               "gives no deviation. The current default of 125 Hz is an inference "
               "from the basestation sensitivity figure, nothing more.",
        "setup": [
            "Same single-channel capture as M2 - no new recording needed if that "
            "one reached 15 dB SNR.",
            "GPSDO lock is mandatory here. At 920 MHz a 1 ppm error is 920 Hz, "
            "which may be seven times the quantity you are trying to measure.",
        ],
        "procedure": [
            "Run the demodulator with --symbol-rate-max narrowed towards the "
            "expected rate. This is the highest-leverage setting for accuracy.",
            "Read the deviation figure and the modulation index h.",
            "Confirm the reported carrier offset is small and stable. A large or "
            "drifting offset means your reference is not locked.",
            "Re-run with --symbol-rate-max at half and at double your first value. "
            "The deviation figure should not move materially. If it does, the "
            "filter is interacting with the measurement and you should trust the "
            "narrowest setting that still reports a reliable symbol rate.",
            "Repeat on captures from at least 3 different devices.",
        ],
        "commands": [
            "./unb_demod.py ch_deep.sigmf-data --symbol-rate-max 1000 \\",
            "    --json-out m3_dev.json",
            "",
            "# Then confirm insensitivity to the filter setting:",
            "./unb_demod.py ch_deep.sigmf-data --symbol-rate-max 600",
            "./unb_demod.py ch_deep.sigmf-data --symbol-rate-max 2000",
        ],
        "expect": "A deviation between roughly 100 Hz and 2 kHz. Low h (around 0.5) "
                  "is the reading consistent with the published sensitivity; high h "
                  "(around 4) is what Carson's rule gives against \"a few kHz "
                  "occupied bandwidth\". Either is plausible - the measurement "
                  "settles it.",
        "accept": [
            "At least 30 bursts across at least 3 devices.",
            "Standard deviation under 3 percent of the mean.",
            "Figure stable within 3 percent across the --symbol-rate-max sweep.",
            "Reported carrier offset under 200 Hz and not drifting between bursts.",
            "All contributing bursts at 15 dB SNR or better. Below 8 dB the "
            "deviation estimate degrades badly - see the accuracy table.",
        ],
        "fail": [
            "<b>Deviation changes when you change --symbol-rate-max.</b> The IF "
            "filter is clipping the modulation. Widen --if-bandwidth explicitly "
            "and re-run.",
            "<b>Carrier offset of several hundred Hz or more.</b> Reference not "
            "locked, or the wrong channel centre. Fix before recording a number.",
            "<b>Deviation varies by more than 10 percent between devices.</b> Do not "
            "average it away. Either the devices genuinely differ, or one capture "
            "is bad. Investigate before baking anything in.",
        ],
    },
    {
        "id": "M4",
        "title": "Exact symbol rate",
        "pins": "UNB_DEFAULT_SYMBOL_RATE (telensa.hpp:74)",
        "why": "The FCC report says 500 bps, which is almost certainly a rounded "
               "figure. The exact value reveals the reference oscillator the "
               "designers used, and any error here accumulates across a 200-bit "
               "frame until bit slicing fails.",
        "setup": [
            "Same capture as M3. GPSDO locked - a rate measurement inherits your "
            "reference error directly.",
        ],
        "procedure": [
            "Read the symbol rate from the same run as M3.",
            "Confirm it is not flagged [UNRELIABLE]. If it is, narrow "
            "--symbol-rate-max and --if-bandwidth and re-run.",
            "Compare the mean across at least 30 bursts.",
            "Check the figure against plausible crystal divisions. A rate of "
            "500.00 bps suggests a synthesised clock; something like 488.28 bps "
            "would be a power-of-two division of a 32.768 kHz or 16 MHz reference "
            "and is a strong hint about the hardware.",
        ],
        "commands": [
            "python3 -c \"import json; d=json.load(open('m3_dev.json'));\\",
            "  r=[x['symbol_rate_bps'] for x in d if x['rate_reliable']];\\",
            "  print(len(r), sum(r)/len(r))\"",
        ],
        "expect": "A tight cluster. The symbol rate estimator holds to under 0.15 "
                  "percent even at low SNR once the burst is centred and filtered, "
                  "so the spread should be very small.",
        "accept": [
            "At least 30 bursts, none flagged [UNRELIABLE].",
            "Standard deviation under 0.5 percent of the mean.",
            "Consistent across at least 3 devices and 2 separate sessions.",
        ],
        "fail": [
            "<b>Flagged [UNRELIABLE] throughout.</b> Either SNR is too low, or the "
            "signal has no alternating preamble so the spectral cross-check cannot "
            "corroborate. Check the rate_fit_quality field in the JSON: above 0.8 "
            "the timing measurement is sound even without corroboration.",
            "<b>Rate differs between sessions.</b> Suspect your own reference "
            "before suspecting the transmitter.",
        ],
    },
    {
        "id": "M5",
        "title": "Preamble pattern and length",
        "pins": "field_preamble default (ui_telensa_tx.cpp:162) and the 0x55 "
                "pattern in build_frame() (telensa.cpp)",
        "why": "The preamble is the receiver's clock-recovery anchor and the first "
               "thing you can positively identify in a bitstream. Its length also "
               "tells you how much of the ~400 ms burst is overhead.",
        "setup": ["Bits recovered from the M3/M4 capture."],
        "procedure": [
            "Export bits with --bits-out.",
            "Inspect the leading bits of several bursts by eye. An alternating "
            "1010... run is the preamble.",
            "Count its length in bits, and check whether it is the same in every "
            "burst.",
            "Note the value reported as preamble@N by the demodulator - N is where "
            "the alternating run starts, which also tells you your bit alignment.",
        ],
        "commands": [
            "./unb_demod.py ch_deep.sigmf-data --symbol-rate-max 1000 \\",
            "    --bits-out m5_bits.txt",
            "head -3 m5_bits.txt | cut -c1-96",
        ],
        "expect": "A run of alternating bits, most likely 32 to 128 bits, followed "
                  "by a non-alternating pattern - that transition is the start of "
                  "the sync word.",
        "accept": [
            "Identical preamble length in at least 20 consecutive bursts.",
            "Pattern confirmed as strictly alternating, or the actual pattern "
            "recorded verbatim if it is not.",
        ],
        "fail": [
            "<b>No alternating run.</b> Possible but unusual. Record the leading "
            "bits verbatim and do not force a 0x55 assumption into the firmware.",
            "<b>Length varies between bursts.</b> Check bit alignment first - a "
            "one-bit slip makes a constant preamble look variable.",
        ],
    },
    {
        "id": "M6",
        "title": "Sync word",
        "pins": "sym_sync default 0x2DD4 (ui_telensa_tx.cpp:163)",
        "why": "0x2DD4 is a conventional placeholder borrowed from common radio "
               "practice. It has no connection to PLANet. Everything downstream "
               "depends on aligning frames correctly, and the sync word is the "
               "alignment anchor.",
        "setup": ["Bit file from M5."],
        "procedure": [
            "Take the bits immediately following the preamble in one burst.",
            "Look for the same run at the same position in every other burst. "
            "That common run is the sync word.",
            "Determine its length by extending until the bits stop being common "
            "across all bursts.",
            "Verify by re-running the frame analyser with the candidate. If every "
            "burst aligns, it is correct.",
        ],
        "commands": [
            "# Run without --sync first to see raw structure:",
            "./unb_frames.py m5_bits.txt",
            "",
            "# Then confirm the candidate aligns every burst:",
            "./unb_frames.py m5_bits.txt --sync <candidate-hex> --drop-sync",
        ],
        "expect": "The field map will show a constant run after the preamble. "
                  "\"0 burst(s) lacked it\" confirms the candidate.",
        "accept": [
            "Candidate found in 100 percent of at least 30 bursts.",
            "Present in bursts from at least 3 different devices - a sync word is "
            "protocol-wide, so if it varies per device it is not a sync word.",
        ],
        "fail": [
            "<b>No constant run after the preamble.</b> The frame may be whitened "
            "from the first payload bit. Try M7's whitening check before assuming "
            "there is no sync word.",
            "<b>Candidate found in only some bursts.</b> Either two frame types "
            "exist, or alignment is slipping. Separate the bursts by length first.",
        ],
    },
    {
        "id": "M7",
        "title": "Frame layout: address, payload, CRC",
        "pins": "Nothing yet - this measurement is what justifies writing a real "
                "encoder alongside build_frame() instead of the placeholder.",
        "why": "This is the measurement that needs deliberate experimental design "
               "rather than just a good capture. Addressing and protocol constants "
               "are indistinguishable in a single-device capture: both are simply "
               "constant. The contrast between devices is the only thing that "
               "separates them.",
        "setup": [
            "<b>At least 3 devices</b>, captured back to back with everything else "
            "held constant.",
            "Serial numbers recorded and matched to capture filenames. This is the "
            "step people skip and cannot recover later.",
        ],
        "procedure": [
            "Capture at least 10 bursts from each device separately.",
            "Build a combined bit file with one device label per line, in the form "
            "label:bits - the tool needs the labels to do the addressing analysis.",
            "Run the frame analyser aligned on the M6 sync word.",
            "Read the field map. Constant runs are protocol constants. Positions "
            "constant within a device but differing between devices are address "
            "candidates. Freely varying positions are payload, counter or CRC.",
            "Run the CRC search. It requires every frame to validate under the "
            "same variant, so a match across 3+ frames is trustworthy.",
            "If everything after the sync word is high entropy with no constants "
            "at all, suspect whitening - but rule out misalignment first, because "
            "misaligned frames also look uniformly random.",
        ],
        "commands": [
            "# Combine per-device bit files with labels:",
            "awk '{print \"cellA:\"$0}' bits_A.txt  > m7_all.txt",
            "awk '{print \"cellB:\"$0}' bits_B.txt >> m7_all.txt",
            "awk '{print \"cellC:\"$0}' bits_C.txt >> m7_all.txt",
            "",
            "./unb_frames.py m7_all.txt --sync <sync-hex> --drop-sync --crc-search",
        ],
        "expect": "A field map with identifiable regions, an address candidate run "
                  "of 8 to 32 bits, and ideally a CRC match naming a standard "
                  "variant and the span it covers.",
        "accept": [
            "At least 3 devices, at least 10 bursts each.",
            "Address candidate run is contiguous and the same width for all "
            "devices.",
            "If a CRC is found, it validates on 100 percent of frames from all "
            "devices - not just the ones used to find it.",
            "Payload regions correlate with something you deliberately changed. "
            "If you cannot make a field move by acting on the system, you have "
            "not identified it, only located entropy.",
        ],
        "fail": [
            "<b>Uniformly high entropy, no constants.</b> Check alignment, then "
            "test common LFSR whitening polynomials. A de-whitened stream shows "
            "structure immediately.",
            "<b>No CRC match.</b> It may be a different width, cover a "
            "non-byte-aligned span, sit somewhere other than the tail, or the frame "
            "may be whitened. Not a failure of the campaign - record and move on.",
            "<b>Address candidates scattered rather than contiguous.</b> Often "
            "means the address is bit-interleaved or the frames are misaligned by "
            "differing amounts. Re-check per-device alignment individually.",
        ],
    },
    {
        "id": "M8",
        "title": "Hop sequence and reproducibility",
        "pins": "HopSequencer LFSR seed and polynomial (telensa.cpp:78/87, "
                "telensa.hpp:117/121)",
        "why": "15.247 requires a pseudo-random channel list with roughly equal "
               "average use. Whether the sequence repeats after a power cycle is "
               "the decisive experiment: a repeating sequence means a seeded "
               "generator, which is reproducible; a non-repeating one means it is "
               "derived from time or node identity, which is not.",
        "setup": [
            "Wideband capture covering the whole band, as M1.",
            "Ability to power-cycle a device under controlled conditions.",
        ],
        "procedure": [
            "Record a long wideband capture - hours, not minutes - and log "
            "detections with --hop-report.",
            "Extract the ordered channel sequence from the CSV.",
            "Power-cycle the device. Record again under identical conditions.",
            "Compare the two sequences from their respective starts. Identical "
            "means a seeded PRNG. Different means time or identity derived.",
            "Check that channel usage is roughly uniform across the band, as the "
            "regulation requires. A strong bias is informative.",
            "Measure the revisit interval per channel and compare against the "
            "dwell limits in section 6.",
        ],
        "commands": [
            "./unb_survey.py long_run_1.cs16 --sample-rate 10000000 \\",
            "    --center 922500000 --csv m8_run1.csv --hop-report",
            "",
            "# After power cycle:",
            "./unb_survey.py long_run_2.cs16 --sample-rate 10000000 \\",
            "    --center 922500000 --csv m8_run2.csv --hop-report",
            "",
            "diff <(cut -d, -f2 m8_run1.csv) <(cut -d, -f2 m8_run2.csv) | head",
        ],
        "expect": "A sequence visiting many channels with roughly equal frequency. "
                  "The two runs will either match from the start or diverge "
                  "immediately - there is rarely a middle case.",
        "accept": [
            "At least 200 detections per run, covering at least 50 channels.",
            "Reproducibility result the same across at least 2 power cycles.",
            "Channel usage histogram recorded, whether uniform or not.",
        ],
        "fail": [
            "<b>Too few detections to see a pattern.</b> Extend the capture or "
            "stimulate harder. Hop analysis is the most data-hungry measurement "
            "here; budget hours.",
            "<b>Sequences match for a while then diverge.</b> Suggests a seeded "
            "generator that is re-seeded periodically or resynchronised to the "
            "basestation. Note where divergence begins.",
        ],
    },
]


def cover(story):
    story += [
        Spacer(1, 42 * mm),
        P("UNB FSK Measurement Field Manual", "Cover"),
        Spacer(1, 4 * mm),
        P("Pinning down the unknowns in the PortaPack UNB FSK TX app", "CoverSub"),
        Spacer(1, 14 * mm),
        callout(
            "Read section 1 before connecting anything",
            "A 4 W basestation into an unattenuated receiver front end will destroy "
            "it. Section 1.3 is a level budget, not a formality. Section 1.4 "
            "validates your measurement chain against a known signal - if you skip "
            "it, you will not be able to tell a surprising result from a broken "
            "setup, and you will have no way to ask.",
        ),
        Spacer(1, 10 * mm),
        P(f"Generated {datetime.date.today().isoformat()} &nbsp;|&nbsp; "
          "Companion to tools/telensa/ and "
          "firmware/application/external/telensa_tx/", "CoverSub"),
        Spacer(1, 20 * mm),
        callout(
            "Scope",
            "The physical layer targeted here is publicly confirmed. The protocol "
            "is not. Frame structure, deviation, hop generation and the Asia-variant "
            "band plan are proprietary and unpublished; the 920-925 MHz plan is "
            "inferred from Hong Kong regulation, not from a vendor statement. This "
            "manual measures a radio link. It does not describe, and the "
            "accompanying app cannot produce, valid PLANet protocol frames.",
            bg=SHADE, border=ACCENT,
        ),
        PageBreak(),
    ]


def section_how_to_use(story):
    story += [
        P("0. How to use this manual", "H1"),
        P("Every measurement below converts one editable placeholder in the "
          "firmware into a measured constant. The procedures are ordered by "
          "dependency: M1 establishes where to look, M2 to M4 characterise the "
          "physical layer, M5 to M7 open up the frame, and M8 addresses hopping. "
          "Work them in order - later measurements assume the earlier results."),
        P("Each procedure has the same shape:"),
        *bullets([
            "<b>Pins down</b> - the firmware value this measurement fixes, with "
            "its file and line.",
            "<b>Why it matters</b> - so you can judge whether a shortcut is safe.",
            "<b>Setup</b> and <b>Procedure</b> - the handholding part.",
            "<b>Expected result</b> - what a correct outcome looks like.",
            "<b>Acceptance criteria</b> - the gate a value must pass before it is "
            "baked in.",
            "<b>If it goes wrong</b> - the failure modes worth recognising.",
        ]),
        P("The acceptance criteria are the important part.", "H2"),
        P("A single clean burst is never sufficient evidence to bake in a "
          "constant. A systematic error - an unlocked reference, an asymmetric "
          "filter, a mis-set centre frequency - reproduces perfectly across every "
          "burst in a session. Consistency within one capture proves only that "
          "the error is stable. That is why the criteria call for multiple "
          "devices, multiple sessions, and in one case a deliberate sweep of an "
          "analysis parameter to prove the measurement is not an artefact of the "
          "tooling."),
        callout(
            "The bake-in rule",
            "A value graduates from editable field to compiled constant only when "
            "it has met every acceptance criterion listed for its measurement. "
            "Until then it stays editable, even if you are confident. Section 5 "
            "records the gate for each value and where to make the edit.",
            bg=SHADE, border=ACCENT,
        ),
        PageBreak(),
    ]


def section_preflight(story):
    story += [
        P("1. Pre-flight", "H1"),
        P("1.1 Equipment checklist", "H2"),
        table([
            ["", "Item", "Requirement", "Why"],
            ["[ ]", "10 MHz reference", "GPSDO or OCXO, ~1 ppb",
             "Mandatory. See 1.2 - this is the most likely thing to invalidate "
             "the campaign."],
            ["[ ]", "SDR, characterisation", "External clock input; 250 ksps+, 16-bit",
             "USRP B210, Airspy R2, or HackRF via CLKIN"],
            ["[ ]", "SDR, wideband", "8-10 Msps, covers 5 MHz in one capture",
             "Stepped sweeps miss a sparse hopper"],
            ["[ ]", "Band-pass filter", "902-928 or 920-925 MHz",
             "Keeps mobile downlink and harmonics out of the front end"],
            ["[ ]", "Step attenuator", "30-40 dB, adequate power rating",
             "Front-end protection. See 1.3"],
            ["[ ]", "Antennas", "Two", "Separating uplink from downlink by "
             "position and polarisation"],
            ["[ ]", "PortaPack + UNB FSK TX", "App built and installed",
             "Calibration source for 1.4"],
            ["[ ]", "Toolkit", "tools/telensa/, numpy installed",
             "Run 1.4 before you travel, not on arrival"],
            ["[ ]", "Storage", "See 1.6", "Wideband captures are large"],
        ], [10 * mm, 34 * mm, 46 * mm, 78 * mm], mono_cols=()),

        P("1.2 Verify the reference is actually locked", "H2"),
        P("Do not take a front-panel LED as proof. Measure it."),
        *steps([
            "Set the PortaPack UNB FSK TX app to a known channel and start "
            "continuous transmission at low power, well attenuated.",
            "Receive it on the characterisation SDR and run the demodulator.",
            "Read the reported carrier offset. With both ends locked to the same "
            "reference it should be within a few Hz and stable burst to burst.",
            "Disconnect the GPSDO and repeat. The offset should visibly worsen. "
            "If it does not change at all, your SDR is not using the external "
            "reference and you must fix that before proceeding.",
        ]),
        callout(
            "Why this matters more than anything else here",
            "The deviation you are trying to measure in M3 may be as small as "
            "125 Hz. At 920 MHz, a 1 ppm reference error is 920 Hz - seven times "
            "the quantity of interest. An unlocked receiver does not give you a "
            "slightly wrong answer; it gives you a meaningless one, and nothing "
            "in the recorded numbers will look obviously wrong afterwards.",
        ),

        P("1.3 Level budget and front-end protection", "H2"),
        P("A basestation transmits 4 W EIRP - 36 dBm. Inside a screened "
          "enclosure there is no free-space loss to save you. Work out the "
          "attenuation before connecting, not after."),
        table([
            ["Quantity", "Figure", "Note"],
            ["Basestation TX", "+36 dBm EIRP", "BS4 manual, US configuration"],
            ["Telecell TX", "+14 to +20 dBm ERP", "25-100 mW, datasheet"],
            ["Typical SDR damage threshold", "around 0 dBm",
             "Check your specific hardware; some are lower"],
            ["Typical SDR compression onset", "-20 to -10 dBm",
             "Above this, measurements are distorted even without damage"],
            ["Target level at the SDR input", "-40 to -25 dBm",
             "Comfortable, with headroom for bursts"],
            ["Attenuation therefore needed", "50 to 75 dB from a basestation",
             "Cable and enclosure coupling loss counts towards this"],
        ], [52 * mm, 40 * mm, 76 * mm]),
        *steps([
            "Start with maximum attenuation - more than you think you need.",
            "Confirm you can see the signal at all, then reduce attenuation in "
            "10 dB steps until it sits in the target window.",
            "Check for compression: if reducing attenuation by 10 dB does not "
            "raise the reported level by about 10 dB, you are compressed. Back "
            "off.",
            "Record the final attenuation in the capture log. It is needed to "
            "reconstruct absolute levels later.",
        ]),

        P("1.4 Validate the measurement chain", "H2"),
        P("Run this before travelling and again after any change to the setup. "
          "It takes two minutes and it is the only thing standing between you and "
          "an unresolvable ambiguity on site."),
        cmd("cd tools/telensa",
            "./unb_selftest.py --out selftest.cs16",
            "./unb_demod.py selftest.cs16 --expect-rate 500 --expect-deviation 125"),
        P("Expect two PASS lines. Then run the harder cases so you recognise the "
          "failure modes when they appear on real data:"),
        cmd("# Low SNR plus a clock error. Both should PASS.",
            "./unb_selftest.py --out hard.cs16 --snr 10 --freq-offset 900",
            "./unb_demod.py hard.cs16 --symbol-rate-max 1000 \\",
            "    --expect-rate 500 --expect-deviation 125",
            "",
            "# Where deviation breaks down. Expect a FAIL - this is correct.",
            "./unb_selftest.py --out worse.cs16 --snr 6 --freq-offset 900",
            "./unb_demod.py worse.cs16 --symbol-rate-max 1000 --expect-deviation 125"),
        P("If the first test does not pass, stop and fix the toolkit. Do not "
          "proceed to real captures with a chain you have not verified."),

        P("1.5 Stimulating the system", "H2"),
        P("Traffic is sparse by design: telecells hold their schedules locally "
          "and report rarely. Waiting is the slow path, and having the hardware in "
          "a cage means you do not have to. In rough order of usefulness:"),
        *bullets([
            "<b>Power-cycle a telecell.</b> Association and commissioning traffic "
            "is the densest and most structured you will see, and the most likely "
            "place for addressing to appear in the clear.",
            "<b>Occlude the light sensor</b> to force a dusk or dawn switching "
            "transition.",
            "<b>Force a fault</b> - open the lamp circuit, pull the load - to "
            "trigger fault reporting.",
            "<b>NFC provisioning.</b> Documented as a feature; what it exchanges "
            "is not. Capture the RF side during and just after provisioning.",
            "<b>Change exactly one thing at a time, and write it down.</b> M7 is "
            "impossible without this discipline.",
        ]),
        P("Keep a common time reference between your stimulus log and your "
          "captures. Correlating \"pulled the load at T\" with \"burst appeared at "
          "T plus 2.3 s\" is most of the analysis."),

        P("1.6 Storage planning", "H2"),
        table([
            ["Configuration", "Rate", "Per hour", "Use"],
            ["10 Msps, cs8", "20 MB/s", "72 GB", "M1, M8 - log only, do not keep IQ"],
            ["2 Msps, cs8", "4 MB/s", "14 GB", "Wideband, short captures"],
            ["250 ksps, cs16", "1 MB/s", "3.6 GB", "M2 to M7 - keep this IQ"],
        ], [44 * mm, 24 * mm, 24 * mm, 76 * mm]),
        P("For the long wideband runs, record detections rather than IQ. A full "
          "day at 10 Msps is about 1.7 TB; the same day as a detection log is a "
          "few hundred kilobytes. Keep IQ only for bursts you intend to "
          "demodulate."),
        PageBreak(),
    ]


def section_targets(story):
    story += [
        P("2. What needs pinning down", "H1"),
        P("Every value below is currently an editable field or a documented "
          "inference. The right-hand column names the measurement that fixes it."),
        table([
            ["Value", "Current setting", "Basis", "Fixed by"],
            ["FSK deviation", "125 Hz", "Inference from basestation sensitivity. "
             "Not published in any form.", "M3"],
            ["Symbol rate", "500 bps", "FCC test report, but almost certainly "
             "rounded", "M4"],
            ["Channel 0 centre, Asia", "920.0125 MHz", "Inferred from HK "
             "regulation, not a vendor statement", "M1"],
            ["Channel count, Asia", "200", "Derived from the inferred band and "
             "raster", "M1"],
            ["Channel raster", "25 kHz", "FCC test report - confirmed for the US "
             "variant, assumed retained", "M1"],
            ["Preamble length", "8 bytes of 0x55", "Conventional placeholder", "M5"],
            ["Sync word", "0x2DD4", "Conventional placeholder, no connection to "
             "PLANet", "M6"],
            ["Frame layout", "None - generic placeholder", "Entirely proprietary",
             "M7"],
            ["Hop generator", "16-bit LFSR, seed 0xACE1", "Bench substitute, not "
             "an attempt to reproduce theirs", "M8"],
            ["Burst length", "Derived from frame size", "FCC report gives "
             "399.25 ms occupancy", "M2"],
        ], [38 * mm, 32 * mm, 76 * mm, 18 * mm]),
        callout(
            "One asymmetry worth planning for",
            "The telecell receive sensitivity is 15 dB worse than the "
            "basestation's. That gap is larger than component cost alone explains "
            "and hints at a wider downlink receive filter, a higher downlink "
            "symbol rate, or a shorter integration window on the node side. If M3 "
            "and M4 give different answers for uplink and downlink bursts, that is "
            "a real finding, not an error - record both separately rather than "
            "averaging them.",
            bg=SHADE, border=ACCENT,
        ),
        PageBreak(),
    ]


def render_measurement(story, m):
    story += [
        P(f"{m['id']}. {m['title']}", "H1"),
        table([["Pins down", m["pins"]]], [26 * mm, 142 * mm], header=False),
        Spacer(1, 3 * mm),
        P("Why it matters", "H3"),
        P(m["why"]),
        P("Setup", "H3"),
        *bullets(m["setup"]),
        P("Procedure", "H3"),
        *steps(m["procedure"]),
    ]

    if m.get("commands"):
        story.append(cmd(*[c if c else "&nbsp;" for c in m["commands"]]))

    story += [
        P("Expected result", "H3"),
        P(m["expect"]),
        KeepTogether([
            P("Acceptance criteria - all must hold before baking in", "H3"),
            *bullets(m["accept"]),
        ]),
        P("If it goes wrong", "H3"),
        *bullets(m["fail"]),
        PageBreak(),
    ]


def section_bake_in(story):
    story += [
        P("5. Baking in a measured value", "H1"),
        P("When a value has met every acceptance criterion for its measurement, "
          "make the edit below. Change the comment at the same time: each "
          "placeholder is currently annotated as an inference, and that annotation "
          "must become a citation of your measurement - date, session, sample "
          "size. A constant with a stale comment claiming it is a guess is nearly "
          "as bad as a guess."),
        table([
            ["Value", "Edit here", "Also update"],
            ["FSK deviation", "telensa.hpp:73 UNB_DEFAULT_DEVIATION",
             "The comment above it, which currently explains the h=0.5 inference"],
            ["Symbol rate", "telensa.hpp:74 UNB_DEFAULT_SYMBOL_RATE",
             "Nothing else - samples_per_bit derives from it"],
            ["Asia channel plan", "telensa.cpp:33 band_defs[BAND_HK]",
             "The comment marking it INFERRED, and README section 1"],
            ["Channel raster", "telensa.hpp:67 UNB_CHANNEL_SPACING",
             "All three band_defs channel counts depend on this"],
            ["Preamble", "ui_telensa_tx.cpp:162, and build_frame() if the "
             "pattern is not 0x55", "telensa.hpp scope comment"],
            ["Sync word", "ui_telensa_tx.cpp:163 sym_sync.set_value()",
             "telensa.hpp scope comment"],
            ["Frame layout", "New encoder alongside build_frame() in telensa.cpp",
             "Do not redefine the placeholder - add beside it, per the note in "
             "telensa.hpp"],
            ["Hop generator", "telensa.cpp:78/87 and telensa.hpp:117/121",
             "The comment disclaiming any relationship to Telensa's generator"],
        ], [30 * mm, 62 * mm, 76 * mm]),
        callout(
            "If a measurement contradicts the public record",
            "Record what you measured, and keep the citation to what was "
            "published alongside it. A conflict between a vendor filing and your "
            "bench is a finding in its own right, and the next person needs both "
            "numbers to make sense of it. Do not quietly overwrite one with the "
            "other.",
            bg=SHADE, border=ACCENT,
        ),
        P("Regenerating this manual", "H2"),
        P("The line references above are baked into make_field_manual.py. If you "
          "move a constant, update the manual generator and regenerate, so the "
          "document does not drift out of step with the code:"),
        cmd("python3 make_field_manual.py --out UNB_FSK_Field_Manual.pdf"),
        PageBreak(),
    ]


def section_sheets(story):
    story += [
        P("6. Recording sheets", "H1"),
        P("Photocopy or reproduce these. The fields that get omitted in the "
          "moment are the ones that make a capture unusable later - especially "
          "\"what was stimulated\" and the reference lock state."),

        P("6.1 Capture log", "H2"),
        blank_rows(
            ["File", "Time", "Centre", "Rate", "Att. dB", "Lock?", "Device",
             "Stimulus"],
            [30 * mm, 16 * mm, 22 * mm, 18 * mm, 16 * mm, 13 * mm, 20 * mm,
             33 * mm],
            16),
        Spacer(1, 5 * mm),

        P("6.2 M3 deviation results", "H2"),
        blank_rows(
            ["Capture", "Device", "Bursts", "Mean dev Hz", "SD Hz", "h",
             "Offset Hz", "SNR dB"],
            [32 * mm, 20 * mm, 16 * mm, 24 * mm, 16 * mm, 14 * mm, 20 * mm,
             26 * mm],
            12),
        Spacer(1, 3 * mm),
        table([["Sweep check", "--symbol-rate-max at half: ______ Hz &nbsp;&nbsp; "
                "nominal: ______ Hz &nbsp;&nbsp; double: ______ Hz &nbsp;&nbsp; "
                "stable within 3%? [ ] yes [ ] no"]],
              [30 * mm, 138 * mm], header=False),
        Spacer(1, 5 * mm),

        P("6.3 M4 symbol rate results", "H2"),
        blank_rows(
            ["Capture", "Device", "Session", "Bursts", "Mean bps", "SD bps",
             "Any UNRELIABLE?"],
            [32 * mm, 22 * mm, 20 * mm, 18 * mm, 24 * mm, 20 * mm, 32 * mm],
            10),
        PageBreak(),

        P("6.4 M5 to M7 frame findings", "H2"),
        table([
            ["Finding", "Value", "Evidence"],
            ["Preamble pattern", "", ""],
            ["Preamble length (bits)", "", ""],
            ["Sync word", "", ""],
            ["Sync length (bits)", "", ""],
            ["Address offset (bits)", "", ""],
            ["Address width (bits)", "", ""],
            ["CRC variant", "", ""],
            ["CRC span", "", ""],
            ["Whitening suspected?", "", ""],
            ["Frame length (bits)", "", ""],
        ], [42 * mm, 46 * mm, 80 * mm]),
        Spacer(1, 5 * mm),

        P("6.5 M8 hop findings", "H2"),
        table([
            ["Finding", "Run 1", "Run 2 (after power cycle)"],
            ["Detections", "", ""],
            ["Unique channels", "", ""],
            ["Sequence reproducible?", "", ""],
            ["Divergence point, if any", "", ""],
            ["Revisit interval, median", "", ""],
            ["Usage roughly uniform?", "", ""],
        ], [50 * mm, 59 * mm, 59 * mm]),
        Spacer(1, 5 * mm),

        P("6.6 Sign-off: values cleared for bake-in", "H2"),
        blank_rows(
            ["Value", "Measured", "Criteria met?", "By", "Date"],
            [44 * mm, 34 * mm, 30 * mm, 30 * mm, 30 * mm],
            9),
        PageBreak(),
    ]


def section_troubleshooting(story):
    story += [
        P("7. Troubleshooting", "H1"),
        P("7.1 No bursts detected", "H2"),
        P("Work down this list in order. Each step is cheaper than the next."),
        *steps([
            "Lower --threshold. A weak burst may be only a few dB above the floor.",
            "Lower --min-duration in case bursts are shorter than expected.",
            "Check --channel-offset - the signal may not be at DC.",
            "Confirm --sample-rate. A wrong rate breaks everything downstream and "
            "produces confidently wrong numbers rather than an error.",
            "Narrow --symbol-rate-max. This tightens the IF filter and is the "
            "single most effective change for a weak slow signal.",
            "Widen --afc-range if you suspect a large clock offset.",
            "Pass --whole-file if the capture has been pre-trimmed to a single "
            "burst and therefore has no idle region to measure a floor against.",
            "Verify with the selftest that the chain still works at all.",
        ]),

        P("7.2 Symbol rate flagged UNRELIABLE", "H2"),
        *bullets([
            "Check rate_fit_quality in the JSON output. Above 0.8, the timing "
            "measurement is sound even if the spectral cross-check could not "
            "corroborate it - which happens legitimately when there is no "
            "alternating preamble.",
            "Narrow --symbol-rate-max towards the expected rate.",
            "Confirm SNR. The rate estimate is robust once the burst is centred "
            "and filtered, so persistent unreliability usually means the burst is "
            "not being centred - check the reported carrier offset.",
        ]),

        P("7.3 Deviation figure looks implausible", "H2"),
        *bullets([
            "Sweep --symbol-rate-max. If the deviation moves, the IF filter is "
            "clipping the modulation - widen --if-bandwidth explicitly.",
            "Check the carrier offset. A large offset used to compress the "
            "deviation badly; AFC now corrects for it, but only within "
            "--afc-range. Outside that range the burst is simply filtered away.",
            "Confirm SNR is at least 15 dB. Below 8 dB the deviation estimate "
            "degrades to the point of being useless while still looking "
            "plausible.",
        ]),

        P("7.4 Frame analysis shows no structure", "H2"),
        *bullets([
            "Rule out misalignment first. Without a correct sync anchor every "
            "position looks random, which is indistinguishable from whitening.",
            "Separate bursts by length before analysing - two frame types mixed "
            "together will smear every field.",
            "Check bit alignment per device. Different devices may be offset by "
            "different amounts if their captures were trimmed differently.",
            "Only then consider whitening or encryption, and test common LFSR "
            "polynomials before concluding it is crypto.",
        ]),

        P("7.5 Accuracy reference", "H2"),
        P("Measured against synthetic signals at 500 bps, h = 0.5, with "
          "--symbol-rate-max 1000. SNR is quoted across the full capture "
          "bandwidth, which is the pessimistic convention - in-band SNR after the "
          "IF filter is considerably better."),
        table([
            ["Capture SNR", "Deviation error", "Symbol rate error", "Verdict"],
            ["20 dB or better", "under 1%", "under 0.1%", "Both trustworthy"],
            ["15 dB", "about 1.4%", "under 0.1%", "Both trustworthy - target this"],
            ["10 to 12 dB", "2 to 3%", "under 0.1%", "Rate good, deviation marginal"],
            ["8 dB", "about 3.4%", "about 0.1%", "Rate good, deviation weak"],
            ["6 dB", "about 20%", "about 0.15%", "Rate only. Discard deviation"],
        ], [30 * mm, 34 * mm, 36 * mm, 68 * mm]),
        PageBreak(),
    ]


def section_quickref(story):
    story += [
        P("8. Quick reference", "H1"),
        P("8.1 Commands", "H2"),
        cmd("# Validate the chain (do this first, every session)",
            "./unb_selftest.py --out selftest.cs16",
            "./unb_demod.py selftest.cs16 --expect-rate 500 --expect-deviation 125",
            "&nbsp;",
            "# M1  Which band and channels are live",
            "./unb_survey.py wide.cs16 --sample-rate 10000000 --center 922500000 \\",
            "    --band hk --csv m1.csv --hop-report",
            "&nbsp;",
            "# M2-M4  Physical layer on one channel",
            "./unb_demod.py deep.sigmf-data --symbol-rate-max 1000 \\",
            "    --bits-out bits.txt --json-out bursts.json",
            "&nbsp;",
            "# Pull one channel out of a wideband capture",
            "./unb_demod.py wide.cs16 --sample-rate 2000000 --channel-offset -75000",
            "&nbsp;",
            "# M5-M7  Frame structure, needs device labels for addressing",
            "./unb_frames.py all.txt --sync <hex> --drop-sync --crc-search"),

        P("8.2 Settings that matter most", "H2"),
        table([
            ["Setting", "Default", "When to change it"],
            ["--symbol-rate-max", "4000 bps", "Lower towards the true rate. The "
             "highest-leverage setting for weak signals - it also sets the auto "
             "IF bandwidth"],
            ["--if-bandwidth", "2.5x rate max", "Widen if the deviation figure "
             "shifts when you sweep symbol-rate-max"],
            ["--afc-range", "+/-3 kHz", "Widen for a large clock offset; keep "
             "under half the channel spacing so it cannot lock onto the "
             "neighbour"],
            ["--threshold", "10 dB", "Lower for weak bursts"],
            ["--min-duration", "20 ms", "Lower if bursts are shorter than "
             "expected"],
            ["--fft-size (survey)", "8192", "Raise for finer RBW. Aim for "
             "hundreds of Hz, not tens of kHz"],
        ], [34 * mm, 26 * mm, 108 * mm]),

        P("8.3 Figures worth remembering", "H2"),
        table([
            ["Quantity", "Value", "Status"],
            ["Symbol rate", "500 bps", "Confirmed, FCC test report"],
            ["Channel raster", "25 kHz", "Confirmed for US variant"],
            ["Burst occupancy", "399.25 ms in 20 s", "Confirmed, measured by test "
             "house"],
            ["US band", "910.4875 - 919.9875 MHz", "Confirmed"],
            ["EU band, BS TX", "869.40 - 869.65 MHz", "Confirmed, BS4 manual"],
            ["Asia band", "920 - 925 MHz", "INFERRED from HK regulation"],
            ["FSK deviation", "unknown", "Not published. Target of M3"],
            ["Basestation TX", "4 W EIRP (36 dBm)", "Confirmed"],
            ["Telecell TX", "25 - 100 mW ERP", "Confirmed, datasheet"],
            ["Basestation sensitivity", "-139 dBm conducted", "Confirmed"],
            ["Telecell sensitivity", "-124 dBm", "Confirmed - note the 15 dB gap"],
            ["1 ppm at 920 MHz", "920 Hz", "Why the GPSDO is mandatory"],
        ], [44 * mm, 44 * mm, 80 * mm]),

        Spacer(1, 6 * mm),
        callout(
            "Before you leave the site",
            "Check that every capture in the log has its metadata: centre "
            "frequency, sample rate, gain, attenuation, antenna, timestamp, "
            "reference lock state, device serial, and what you stimulated. A "
            "capture missing the last of those cannot contribute to M7 and cannot "
            "be reconstructed afterwards. Confirm the acceptance criteria you "
            "believe you have met, while you are still able to take another "
            "capture.",
        ),
    ]


def make(path):
    doc = BaseDocTemplate(
        path, pagesize=A4,
        leftMargin=21 * mm, rightMargin=21 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="UNB FSK Measurement Field Manual",
        author="Generated by make_field_manual.py",
        subject="Measurement procedures for pinning down UNB FSK unknowns",
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")

    def decorate(canvas, document):
        canvas.saveState()
        if document.page > 1:
            canvas.setStrokeColor(RULE)
            canvas.setLineWidth(0.4)
            y = A4[1] - 13 * mm
            canvas.line(doc.leftMargin, y, A4[0] - doc.rightMargin, y)
            canvas.setFont("Helvetica", 7.6)
            canvas.setFillColor(colors.HexColor("#555555"))
            canvas.drawString(doc.leftMargin, y + 2 * mm,
                              "UNB FSK Measurement Field Manual")
            canvas.drawRightString(A4[0] - doc.rightMargin, y + 2 * mm,
                                   f"Page {document.page}")
            canvas.setFont("Helvetica-Oblique", 7.2)
            canvas.drawCentredString(
                A4[0] / 2, 10 * mm,
                "Physical layer confirmed from public filings. Protocol is "
                "proprietary and unpublished. Not a PLANet implementation.")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=decorate)])

    story = []
    cover(story)
    section_how_to_use(story)
    section_preflight(story)
    section_targets(story)

    story.append(P("3. Measurement procedures", "H1"))
    story.append(P(
        "Work these in order. Later procedures depend on earlier results: M2 "
        "onward need the channel identified by M1, M5 onward need the bits "
        "recovered in M3 and M4, and M7 needs the alignment anchor from M6."))
    story.append(PageBreak())

    for m in MEASUREMENTS:
        render_measurement(story, m)

    section_bake_in(story)
    section_sheets(story)
    section_troubleshooting(story)
    section_quickref(story)

    doc.build(story)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="UNB_FSK_Field_Manual.pdf")
    args = parser.parse_args()

    make(args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
