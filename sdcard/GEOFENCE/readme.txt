Drone Geofence TX  -  scenario files
====================================

This folder holds the GPS L1 C/A scenario files (.C8) used by the
"Geofence TX" app (TX menu). The app spoofs a GNSS solution that places any
receiver inside a chosen no-fly zone, so a compliant drone's onboard geofence
firmware reacts as if it were standing in a restricted area - refusing to
arm / take off, or warning the operator, depending on the model.

Why GPS L1 C/A?
---------------
It is the one signal virtually every compliant consumer / commercial drone
(DJI, Autel, Parrot, Skydio, Yuneec, ...) tracks for positioning and no-fly
enforcement, so targeting it gives the widest possible fleet coverage from a
single transmitter. GLONASS L1 / BeiDou B1 carriers are selectable in the app
for scenarios generated with other tools.

File format
-----------
  - .C8  : 8-bit signed I/Q (sc8), interleaved
  - Sample rate : 2.6 MHz (2600000)
  - Centre frequency : 1575.42 MHz (GPS L1 C/A)

These match the built-in GPS Sim replay path, so files are interchangeable.

Generating a zone file (off-device, with gps-sdr-sim)
-----------------------------------------------------
1. Get a broadcast ephemeris (RINEX) for the day, e.g. "brdc" from NASA CDDIS.
2. Pick the target no-fly-zone coordinate (lat,lon,alt_metres).
3. Run:

     gps-sdr-sim -e brdc -l <LAT>,<LON>,100 -s 2600000 -b 8 -o <CODE>.C8

   Example (London Heathrow):
     gps-sdr-sim -e brdc -l 51.4700,-0.4543,100 -s 2600000 -b 8 -o LHR.C8

4. Copy <CODE>.C8 into this GEOFENCE folder.

Naming convention
-----------------
Name each file after its zone code so the app auto-loads it when that zone is
selected from the list (e.g. LHR.C8, JFK.C8, LAX.C8). The app's "?" button
shows the exact command for the selected zone, including its coordinates.
Any custom .C8 file can also be loaded with "Open file".

More: https://github.com/portapack-mayhem/mayhem-firmware/wiki/GPS-Sim

Legal / safety
--------------
Transmitting GNSS signals is restricted or illegal in most jurisdictions and
affects every GPS receiver in range (phones, vehicles, aircraft, timing
systems) - not just drones. Use only in a shielded/controlled environment or
where you hold explicit authorisation.
