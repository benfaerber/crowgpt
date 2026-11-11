"""Snapping coordinates to a coarse grid — the server's half of `fuzzed`.

The phone is what actually enforces the setting: it snaps before anything is
sent (mobile/src/domain/location.ts, fuzzedCoords). This is the backstop for a
client that got the rule wrong, the same role captures.py plays for
region-only contributors.

A grid, deliberately not random jitter. Jitter fails exactly the person it
protects — fifty captures at home, each displaced independently, average
straight back to the house. Snapping maps every point in a cell to the same
public point, so repetition reveals nothing new.

The published point is the centre of an N-mile cell, so the true location is
never more than half a diagonal away (about 0.7 × N miles). The longitude grid
is sized from the *snapped* latitude so every point in one latitude band shares
one longitude grid; sizing it from the raw latitude would give near-neighbours
slightly different cells, and the averaging leak would be back through the gap.

Snapping is idempotent — a cell centre snaps to itself — which is what lets
this run on coordinates the phone already snapped without moving them again.
Keep the arithmetic identical to the TypeScript twin.
"""

import math

MILES_PER_DEGREE_LAT = 69.0

# Matches DEFAULT_FUZZ_MILES on the phone. Used when a fuzzed contributor's
# capture arrives before their radius does — the two are separate requests and
# nothing orders them.
DEFAULT_FUZZ_MILES = 5


def fuzz_coords(latitude, longitude, miles=DEFAULT_FUZZ_MILES):
    lat_cell = miles / MILES_PER_DEGREE_LAT
    lat = (math.floor(latitude / lat_cell) + 0.5) * lat_cell
    stretch = max(math.cos(math.radians(lat)), 0.01)
    lon_cell = miles / (MILES_PER_DEGREE_LAT * stretch)
    lon = (math.floor(longitude / lon_cell) + 0.5) * lon_cell
    if lon > 180:
        lon -= 360
    if lon < -180:
        lon += 360
    return max(-90.0, min(90.0, lat)), lon



def occurrence_coords(capture, fleet_lat=None, fleet_lon=None, fleet_region=None):
    """Where BirdNET's species-occurrence filter should assume a capture was.

    Its own fix when it has one. Otherwise the fleet's home ground, but only
    for a capture that says nothing about place (a clip dropped on the
    dashboard) or names the home region itself. A capture that names another
    region was recorded *there*: filling in the home ground filtered ten London
    Carrion Crow clips as if they were in Utah, and BirdNET heard a crow in one
    of them. No filter beats the wrong one; the global model still names
    corvids, and each call records that it was not location-filtered.
    """
    if capture.get("latitude") is not None and capture.get("longitude") is not None:
        return capture["latitude"], capture["longitude"]
    region = (capture.get("region") or "").strip().lower()
    home = (fleet_region or "").strip().lower()
    if not region or (home and home in region):
        return fleet_lat, fleet_lon
    return None, None
