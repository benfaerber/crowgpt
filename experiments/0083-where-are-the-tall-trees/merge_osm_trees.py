"""Marry OSM's mapped street trees to the canopy model's heights.

Ben graded the layer against streets he knows and it kept losing: the
satellite CHM merges a street row into one blob and under-measures it. OSM
contributors have mapped 47,848 individual trees across the valley — trunk
positions without heights — and the CHM knows the height at any point. Each
OSM tree gets the max canopy height within ~6 m of its trunk (the CHM pixel
is ~1.2 m, and a crown peak sits metres from the trunk point); trees
reading >= 12 m join the layer (a verified trunk deserves a lower floor than
an anonymous blob), deduped against CHM stands within ~15 m so rows the
blob-layer already carries do not double up.
"""
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as wt

HERE = Path(__file__).resolve().parent
CHM = Path(sys.argv[1])
WEST, SOUTH, EAST, NORTH = -112.05, 40.50, -111.797, 40.90
MIN_OSM_HEIGHT = 12
DEDUPE_M = 15
CROWN_PX = 5


def fetch_osm_trees():
    query = (f'[out:json][timeout:180];node["natural"="tree"]'
             f'({SOUTH},{WEST},{NORTH},{EAST});out skel qt;')
    request = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "cawtalker-0083/merge"})
    with urllib.request.urlopen(request, timeout=300) as response:
        payload = json.load(response)
    return [(e["lat"], e["lon"]) for e in payload["elements"]
            if "lat" in e]


def main():
    trees = fetch_osm_trees()
    print(f"{len(trees)} OSM trees fetched")

    existing = [f for f in json.load(open(HERE / "tall_trees.geojson"))["features"]
                if f["properties"].get("src") != "osm"]
    cell = DEDUPE_M / 111320
    occupied = set()
    for f in existing:
        lon, lat = f["geometry"]["coordinates"]
        occupied.add((round(lat / cell), round(lon / cell)))

    with rasterio.open(CHM) as src:
        lats = [t[0] for t in trees]
        lons = [t[1] for t in trees]
        xs, ys = wt("EPSG:4326", src.crs, lons, lats)
        added, skipped_dupe, skipped_short = [], 0, 0
        for (lat, lon), x, y in zip(trees, xs, ys):
            row, col = src.index(x, y)
            window = src.read(1, window=((row - CROWN_PX, row + CROWN_PX + 1),
                                         (col - CROWN_PX, col + CROWN_PX + 1)),
                              boundless=True, fill_value=0)
            h = int(window.max())
            if h < MIN_OSM_HEIGHT:
                skipped_short += 1
                continue
            key = (round(lat / cell), round(lon / cell))
            if key in occupied:
                skipped_dupe += 1
                continue
            occupied.add(key)
            added.append({
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [round(lon, 6), round(lat, 6)]},
                "properties": {"h": h, "area_m2": 80, "src": "osm"},
            })
    print(f"added {len(added)} OSM trees "
          f"(skipped: {skipped_short} under {MIN_OSM_HEIGHT} m, "
          f"{skipped_dupe} duplicating stands)")

    merged = {"type": "FeatureCollection", "features": existing + added}
    (HERE / "tall_trees.geojson").write_text(json.dumps(merged))
    print(f"layer now {len(merged['features'])} features")


if __name__ == "__main__":
    main()
