"""Tall-canopy layer for any CawScout region: tiles in, one GeoJSON out.

The original run.py covered one region on one CHM tile whose east edge
happened to clip the Wasatch. Leaving the valley breaks both accidents:
Davis and Utah county span 2-3 Meta/WRI tiles each, and around Provo the
mountains sit INSIDE the box — so this builder mosaics across every tile
that intersects the region and masks stands by elevation (Copernicus
GLO-30 over HTTP): the benches stay, the mountainsides go. Without the
mask the trees signal normalises against p99 and mountain forest flattens
every urban stand to ~zero.

OSM's individually-mapped street trees merge in exactly as 0083 measured
they should (trunks get the CHM's max height within ~6 m, >= 12 m joins,
dedupe 15 m against stands), and the same elevation mask applies to them.

    canopy-venv/bin/python build_region.py <region-slug>

Tiles live in DATA_DIR/experiments/0083-chm/*.tif (see README for the
source); regions come from fieldserver.scout.regions so this file and the
scout builder can never disagree about a box.
"""
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window, from_bounds
from scipy import ndimage

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fieldserver" / "src"))
from fieldserver.scout.regions import by_slug  # noqa: E402

DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
TILES = DATA / "experiments" / "0083-chm"
OUT = Path(__file__).resolve().parent

MIN_HEIGHT = 15
POOL = 8                      # ~9.6 m cells
STRIP_ROWS = 8192             # read in strips; a county window is ~6 GB whole
MIN_OSM_HEIGHT = 12
DEDUPE_M = 15
CROWN_PX = 5
#: Above this the Wasatch starts: benches across all three counties top out
#: ~1,550-1,600 m, the foothill forest begins right after. Riparian canyon
#: mouths below the line survive on purpose — canyon-mouth cottonwoods are
#: plausible crow habitat; mountainside conifer is not.
MAX_ELEV_M = 1650

DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
           "Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM/"
           "Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM.tif")


def mercator(lon, lat):
    xs, ys = warp_transform("EPSG:4326", "EPSG:3857", [lon], [lat])
    return xs[0], ys[0]


def tile_stands(path, region):
    """Stands >= MIN_HEIGHT from one tile's overlap with the region, pooled
    strip-wise so a county-sized window never sits in memory at once."""
    with rasterio.open(path) as src:
        left, bottom = mercator(region.west, region.south)
        right, top = mercator(region.east, region.north)
        window = from_bounds(left, bottom, right, top, src.transform)
        try:
            window = window.intersection(
                Window(0, 0, src.width, src.height)
            ).round_offsets().round_lengths()
        except rasterio.errors.WindowError:
            return []
        if window.width <= 0 or window.height <= 0:
            return []
        transform = src.window_transform(window)

        strips = []
        for row0 in range(0, int(window.height), STRIP_ROWS):
            rows = min(STRIP_ROWS, int(window.height) - row0)
            rows -= rows % POOL
            if rows <= 0:
                break
            strip = src.read(1, window=Window(
                window.col_off, window.row_off + row0, window.width, rows))
            h, w = strip.shape
            w -= w % POOL
            strips.append(strip[:, :w].reshape(
                h // POOL, POOL, w // POOL, POOL).max(axis=(1, 3)))
        pooled = np.vstack(strips)

    tall = pooled >= MIN_HEIGHT
    labels, n = ndimage.label(tall)
    if not n:
        return []
    heights = ndimage.maximum(pooled, labels, index=np.arange(1, n + 1))
    sizes = ndimage.sum_labels(tall, labels, index=np.arange(1, n + 1))
    centroids = ndimage.center_of_mass(tall, labels, index=np.arange(1, n + 1))
    cell_m = abs(transform.a) * POOL
    stands = []
    for (row, col), h, size in zip(centroids, heights, sizes):
        x = transform.c + (col + 0.5) * POOL * transform.a
        y = transform.f + (row + 0.5) * POOL * transform.e
        lons, lats = warp_transform("EPSG:3857", "EPSG:4326", [x], [y])
        stands.append((round(lats[0], 6), round(lons[0], 6), int(h),
                       int(size * cell_m * cell_m)))
    return stands


class ElevationMask:
    """Copernicus GLO-30 read straight off S3, one 1-degree COG window per
    corner the region touches."""

    def __init__(self, region):
        self.grids = {}
        lat_floors = range(math.floor(region.south), math.floor(region.north) + 1)
        lon_floors = range(math.floor(region.west), math.floor(region.east) + 1)
        for lat0 in lat_floors:
            for lon0 in lon_floors:
                ns = f"N{lat0:02d}" if lat0 >= 0 else f"S{-lat0:02d}"
                ew = f"W{-lon0:03d}" if lon0 < 0 else f"E{lon0:03d}"
                url = "/vsicurl/" + DEM_URL.format(ns=ns, ew=ew)
                with rasterio.open(url) as src:
                    window = from_bounds(
                        max(region.west, lon0), max(region.south, lat0),
                        min(region.east, lon0 + 1), min(region.north, lat0 + 1),
                        src.transform).round_offsets().round_lengths()
                    self.grids[(lat0, lon0)] = (
                        src.read(1, window=window),
                        src.window_transform(window))

    def elevation(self, lat, lon):
        grid, transform = self.grids[(math.floor(lat), math.floor(lon))]
        row, col = rasterio.transform.rowcol(transform, lon, lat)
        row = min(max(row, 0), grid.shape[0] - 1)
        col = min(max(col, 0), grid.shape[1] - 1)
        return float(grid[row, col])


def fetch_osm_trees(region):
    query = (f'[out:json][timeout:180];node["natural"="tree"]'
             f'({region.south},{region.west},{region.north},{region.east});'
             f'out skel qt;')
    request = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "cawtalker-0083/region"})
    with urllib.request.urlopen(request, timeout=300) as response:
        payload = json.load(response)
    return [(e["lat"], e["lon"]) for e in payload["elements"] if "lat" in e]


def osm_features(region, tiles, occupied, mask):
    trees = fetch_osm_trees(region)
    print(f"{len(trees)} OSM trees fetched")
    cell = DEDUPE_M / 111320
    added, short, dupe, high = [], 0, 0, 0
    for path in tiles:
        with rasterio.open(path) as src:
            xs, ys = warp_transform("EPSG:4326", src.crs,
                                    [t[1] for t in trees], [t[0] for t in trees])
            remaining = []
            for (lat, lon), x, y in zip(trees, xs, ys):
                row, col = src.index(x, y)
                if not (0 <= row < src.height and 0 <= col < src.width):
                    remaining.append((lat, lon))
                    continue
                window = src.read(1, window=(
                    (row - CROWN_PX, row + CROWN_PX + 1),
                    (col - CROWN_PX, col + CROWN_PX + 1)),
                    boundless=True, fill_value=0)
                h = int(window.max())
                if h < MIN_OSM_HEIGHT:
                    short += 1
                    continue
                if mask.elevation(lat, lon) > MAX_ELEV_M:
                    high += 1
                    continue
                key = (round(lat / cell), round(lon / cell))
                if key in occupied:
                    dupe += 1
                    continue
                occupied.add(key)
                added.append({
                    "type": "Feature",
                    "geometry": {"type": "Point",
                                 "coordinates": [round(lon, 6), round(lat, 6)]},
                    "properties": {"h": h, "area_m2": 80, "src": "osm"},
                })
            trees = remaining
    print(f"added {len(added)} OSM trees (skipped: {short} under "
          f"{MIN_OSM_HEIGHT} m, {dupe} duplicating stands, {high} above "
          f"{MAX_ELEV_M} m)")
    return added


def main():
    region = by_slug(sys.argv[1])
    tiles = sorted(TILES.glob("*.tif"))
    if not tiles:
        raise SystemExit(f"no CHM tiles in {TILES} — see README for the source")

    mask = ElevationMask(region)
    print(f"elevation mask loaded ({len(mask.grids)} DEM windows)")

    stands, masked = [], 0
    for path in tiles:
        found = tile_stands(path, region)
        for lat, lon, h, area in found:
            if mask.elevation(lat, lon) > MAX_ELEV_M:
                masked += 1
                continue
            stands.append((lat, lon, h, area))
        if found:
            print(f"{path.name}: {len(found)} stands in window")
    print(f"{len(stands)} stands kept, {masked} masked above {MAX_ELEV_M} m")

    cell = DEDUPE_M / 111320
    occupied = {(round(lat / cell), round(lon / cell))
                for lat, lon, _, _ in stands}
    features = [{
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"h": h, "area_m2": area},
    } for lat, lon, h, area in stands]
    features += osm_features(region, tiles, occupied, mask)

    out = OUT / Path(region.trees_geojson).name
    out.write_text(json.dumps(
        {"type": "FeatureCollection", "features": features}))
    print(f"{len(features)} features -> {out}")


if __name__ == "__main__":
    main()
