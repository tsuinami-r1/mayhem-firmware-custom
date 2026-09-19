Drone Geofence TX  -  scenario files
====================================

This folder holds the GNSS scenario files (.C8) used by the "Geofence TX" app
(TX menu). The app spoofs a GNSS solution that places any receiver inside a
chosen no-fly zone, so a compliant drone's onboard geofence firmware reacts as
if it were standing in a restricted area - refusing to arm / take off, or
warning the operator, depending on the model.

Bands and why it HOPS rather than transmitting them all at once
---------------------------------------------------------------
The HackRF has a single transmit chain: one centre frequency and one bandwidth
at any instant (~20 MHz ceiling, and sustained SD replay realistically caps
around 2.6-4 Msps). The GNSS bands are 14 to 400 MHz apart, so they physically
CANNOT all be radiated simultaneously.

Instead the app time-multiplexes: tick the bands you want and it cycles around
them, retuning and replaying each band's scenario in turn. A receiver that
keeps losing its band every cycle cannot hold a fix.

  Band   Centre freq     Covers
  ----   -------------   ----------------------------------------------
  L1     1575.420 MHz    GPS L1 C/A + Galileo E1 + BeiDou B1C + QZSS L1
  B1I    1561.098 MHz    BeiDou B1I
  GLON   1602.000 MHz    GLONASS L1 (FDMA centre)
  L5     1176.450 MHz    GPS L5 + Galileo E5a + BeiDou B2a
  L2C    1227.600 MHz    GPS L2C

L1 is the highest-value band by far: those four constellations share 1575.42
MHz, so a single L1 transmission covers that whole stack at once. It is ticked
by default.

Controls
--------
  Band tickboxes  Which bands to enforce on. "All" toggles every band / L1 only.
  Rep             Scenario repeats per band before hopping to the next.
  Loop            Keep cycling continuously (on by default).
  Status          "armed: L1,L5" when idle; "TX L1 1/2" while transmitting.

File format
-----------
  - .C8  : 8-bit signed I/Q (sc8), interleaved
  - Sample rate : 2.6 MHz (2600000)
  - One file per band, named <ZONE>_<BAND>.C8 (e.g. HKG_L1.C8, HKG_L5.C8)
  - Optional sidecar <ZONE>_<BAND>.TXT with sample_rate= and center_frequency=

These match the built-in GPS Sim replay path, so files are interchangeable.
For backwards compatibility a plain <ZONE>.C8 is still accepted as the L1 file.

Generating a zone file (off-device, with gps-sdr-sim)
-----------------------------------------------------
1. Get a broadcast ephemeris (RINEX) for the day, e.g. "brdc" from NASA CDDIS.
2. Pick the target no-fly-zone coordinate (lat,lon,alt_metres).
3. Run:

     gps-sdr-sim -e brdc -l <LAT>,<LON>,100 -s 2600000 -b 8 -o <ZONE>_L1.C8

   Example (Hong Kong International):
     gps-sdr-sim -e brdc -l 22.3080,113.9185,100 -s 2600000 -b 8 -o HKG_L1.C8

4. Copy <ZONE>_L1.C8 into this GEOFENCE folder.

Note: gps-sdr-sim only generates GPS L1 C/A. The other bands (B1I, GLON, L5,
L2C) need their own generator; the app simply replays whatever .C8 you drop in
under the matching band name, so any tool that emits 2.6 Msps sc8 will do.

Naming convention
-----------------
Name each file after its zone code and band so the app picks it up when that
zone is selected (HKG_L1.C8, HKG_L5.C8, LHR_L1.C8, ...). Bands with no file are
skipped, and the status line lists the ones that are actually ready. The app's
"?" button shows the exact command for the selected zone, with its coordinates.
Any custom .C8 can also be loaded with "Open file".

Bundled samples (HKG_L1.C8 / HKG_L5.C8) - TEST VECTORS, not a real fix
----------------------------------------------------------------------
These ship so the "HKG Hong Kong" preset and the two-band hop work out of the
box for bench testing. They contain real GPS L1 C/A Gold-code BPSK for a few
PRNs at 2.6 MHz (a different PRN set per band so the hop is visible on a
waterfall), but they have NO navigation-message data, NO per-satellite Doppler
and NO correct code-phase alignment, so a receiver cannot compute a position
from them. Use them to verify file open, duration display, band hopping,
retuning and the spectrum - not to actually place a drone inside Hong Kong
airspace. For a working scenario, regenerate with gps-sdr-sim as above.

The samples are reproducible: firmware/tools/gen_geofence_sample.py
  python3 gen_geofence_sample.py . HKG L1,B1I,GLON,L5,L2C   # full hop set

Legal / safety
--------------
Transmitting GNSS signals is restricted or illegal in most jurisdictions and
affects every GNSS receiver in range (phones, vehicles, aircraft, timing
systems) - not just drones. Hopping across several bands widens that blast
radius rather than narrowing it. Use only in a shielded/controlled environment
or where you hold explicit authorisation.
