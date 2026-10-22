"""0083: a tall-tree scouting map of the Salt Lake valley for finding new crows.

Source: Meta/WRI 1 m global canopy height model, tile 023100000 (EPSG:3857,
~1.19 m px, uint8 metres). The tile's east edge (-111.797) usefully clips the
Wasatch forests that would otherwise drown the map — what remains is the
valley, where the crows are. Heights are pooled to ~10 m cells (max), stands
of >= MIN_HEIGHT metres are labelled, and the result is a GeoJSON plus a
self-contained Leaflet map for a phone.

Run: the scratch venv with rasterio (see README) against a downloaded
chm.tif; pass its path.
"""
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.windows import from_bounds
from scipy import ndimage

CHM = Path(sys.argv[1] if len(sys.argv) > 1 else "chm.tif")
OUT = Path(__file__).resolve().parent
MIN_HEIGHT = 15
POOL = 8                      # ~9.6 m cells
MAX_FEATURES = None  # publish every stand; the map's own gating handles density

# The scouting box: the valley floor and benches, Farmington Bay to Draper.
WEST, SOUTH, EAST, NORTH = -112.05, 40.50, -111.797, 40.90


def mercator(lon, lat):
    xs, ys = warp_transform("EPSG:4326", "EPSG:3857", [lon], [lat])
    return xs[0], ys[0]


def main():
    with rasterio.open(CHM) as src:
        left, bottom = mercator(WEST, SOUTH)
        right, top = mercator(EAST, NORTH)
        window = from_bounds(left, bottom, right, top, src.transform)
        data = src.read(1, window=window)
        transform = src.window_transform(window)

    h, w = data.shape
    h, w = h - h % POOL, w - w % POOL
    pooled = data[:h, :w].reshape(h // POOL, POOL, w // POOL, POOL).max(axis=(1, 3))
    tall = pooled >= MIN_HEIGHT
    print(f"{tall.sum()} tall cells of {tall.size}")

    labels, n = ndimage.label(tall)
    print(f"{n} stands")
    heights = ndimage.maximum(pooled, labels, index=np.arange(1, n + 1))
    sizes = ndimage.sum_labels(tall, labels, index=np.arange(1, n + 1))
    centroids = ndimage.center_of_mass(tall, labels, index=np.arange(1, n + 1))

    # Height first, area second: the old height*log(area) rank quietly
    # starved street rows — South Temple's giants stand as small separated
    # blobs at 10 m pooling and lost to canyon groves. Every stand >= 21 m
    # now survives unconditionally; the 18-20 m band fills what remains.
    order = np.argsort(-heights.astype(float))
    if MAX_FEATURES is not None:
        order = order[:MAX_FEATURES]
    cell_m = abs(transform.a) * POOL
    features = []
    for i in order:
        row, col = centroids[i]
        x = transform.c + (col + 0.5) * POOL * transform.a
        y = transform.f + (row + 0.5) * POOL * transform.e
        lons, lats = warp_transform("EPSG:3857", "EPSG:4326", [x], [y])
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point",
                         "coordinates": [round(lons[0], 6), round(lats[0], 6)]},
            "properties": {"h": int(heights[i]),
                           "area_m2": int(sizes[i] * cell_m * cell_m)},
        })

    geojson = {"type": "FeatureCollection", "features": features}
    (OUT / "tall_trees.geojson").write_text(json.dumps(geojson))

    html = (OUT / "map_template.html").read_text().replace(
        "__DATA__", json.dumps(geojson)).replace(
        "__MIN_HEIGHT__", str(MIN_HEIGHT))
    (OUT / "tall-trees-map.html").write_text(html)
    print(f"wrote {len(features)} stands -> tall-trees-map.html")


if __name__ == "__main__":
    main()
