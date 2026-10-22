"""0084: a scouting score for finding new crow families, to replace the random walk.

Four signals, gridded at 250 m over the valley and combined as a weighted
prior — this is a heuristic, not a fitted model, and its validation is field
trips (each visit's outcome is a label the score can later be checked
against):

- iNaturalist research-grade American Crow observations (direct presence,
  other people's eyes; weighted highest)
- tall canopy stands from 0083 (nest sites)
- OSM greenspace: parks, cemeteries, golf courses, grass (foraging turf)
- OSM water: rivers, streams, ponds
- human food subsidy: OSM fast food, restaurants, supermarkets, picnic
  sites, waste sites and the landfill — the Marzluff finding that crow
  density tracks garbage and lawn, and the reason a walk through the
  food-poor Avenues found nothing
- NEGATIVE: Great Horned Owl observations (the top predator of crow nests;
  the Salt Lake cemetery is owl country, which is exactly why a human
  recommendation to look for crows there was wrong) and, mildly, Cooper's
  Hawk

Cells within the home-territory radius (the kept captures' centroid) are
excluded — the point is NEW families. Targets are greedily separated by
700 m so twenty targets means twenty places, not one park counted twenty
times.

The east-bench districts get a floor. The first run put nine of twenty
targets west of the Jordan — real crow reports (the Parkway is birded), but
owl 0.00 everywhere, which is partly "nobody reports owls there": the owl
penalty falls hardest on the well-watched east bench, and Ben scouts the
east side. Any named district without a target inside DISTRICT_RADIUS_M
gets its best cell appended, ranked after the open field.
"""
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
WEST, SOUTH, EAST, NORTH = -112.05, 40.50, -111.797, 40.90
CELL_M = 250
N_TARGETS = 20
SEPARATION_M = 700
HOME_EXCLUDE_M = 800
# Trees lead now, crow reports second: canopy is the one signal measured
# uniformly everywhere (satellite), while iNat reports carry a measured 2:1
# east/west observer-effort skew (66% of valley robin observations are east
# of the Jordan) — the biased instrument should not be the loudest.
WEIGHTS = {"inat": 0.25, "trees": 0.32, "green": 0.17, "water": 0.12,
           "food": 0.14}
PENALTIES = {"owl": 0.30, "hawk": 0.08}
#: Predator reports are deflated by local birding effort (robin observations
#: as the proxy): twice the eyes report twice the owls, and without this the
#: penalty falls hardest on the best-watched ground — the east bench Ben
#: actually scouts. Floor 0.3 so unbirded areas don't explode the division.
EFFORT_TAXON = "Turdus migratorius"
EFFORT_KERNEL_M = 800
EFFORT_FLOOR = 0.3
KERNELS_M = {"inat": 600, "trees": 400, "green": 400, "water": 500,
             "food": 500, "owl": 500, "hawk": 400}

DISTRICTS = [
    ("Sugar House", 40.7223, -111.8656),
    ("Millcreek", 40.6869, -111.8636),
    ("East Millcreek", 40.7006, -111.8286),
    ("Holladay", 40.6689, -111.8247),
    ("Cottonwood Heights", 40.6197, -111.8104),
]
# 1500 keeps a floor pin recognisably IN its district: at 2500 the Sugar
# House pin drifted to the radius edge by Nibley golf course and its
# presence then satisfied Millcreek's check too.
DISTRICT_RADIUS_M = 1500

M_PER_LAT = 110_540
M_PER_LON = 111_320 * math.cos(math.radians((SOUTH + NORTH) / 2))


def fetch_inat(taxon="Corvus brachyrhynchos"):
    # One vote per observer per ~275 m: twenty uploads of the same resident
    # birds by one devotee are one fact about crows and twenty about the
    # devotee. Measured 2026-08-21: a single observer held 20 of 24 crow
    # observations in the Taylorsville cluster that ranked four targets.
    points, seen, page = [], set(), 1
    while True:
        url = ("https://api.inaturalist.org/v1/observations"
               f"?taxon_name={urllib.parse.quote(taxon)}"
               f"&nelat={NORTH}&nelng={EAST}&swlat={SOUTH}&swlng={WEST}"
               f"&quality_grade=research&per_page=200&page={page}")
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = json.load(response)
        for obs in payload["results"]:
            loc = obs.get("location")
            if not loc:
                continue
            lat, lon = (float(x) for x in loc.split(","))
            login = (obs.get("user") or {}).get("login", "")
            key = (login, round(lat / 0.0025), round(lon / 0.0025))
            if key in seen:
                continue
            seen.add(key)
            points.append((lat, lon))
        if page * 200 >= payload["total_results"] or page >= 5:
            return points
        page += 1


def fetch_osm():
    query = f"""[out:json][timeout:90];
(
  way["leisure"~"park|golf_course"]({SOUTH},{WEST},{NORTH},{EAST});
  way["landuse"~"cemetery|grass|recreation_ground"]({SOUTH},{WEST},{NORTH},{EAST});
  relation["leisure"="park"]({SOUTH},{WEST},{NORTH},{EAST});
);
out center;
(
  way["waterway"~"river|stream|canal"]({SOUTH},{WEST},{NORTH},{EAST});
  way["natural"="water"]({SOUTH},{WEST},{NORTH},{EAST});
);
out center;
(
  node["amenity"~"fast_food|restaurant|waste_disposal|waste_transfer_station"]({SOUTH},{WEST},{NORTH},{EAST});
  node["shop"="supermarket"]({SOUTH},{WEST},{NORTH},{EAST});
  node["tourism"="picnic_site"]({SOUTH},{WEST},{NORTH},{EAST});
  way["landuse"="landfill"]({SOUTH},{WEST},{NORTH},{EAST});
  way["amenity"~"fast_food|restaurant"]({SOUTH},{WEST},{NORTH},{EAST});
  way["shop"="supermarket"]({SOUTH},{WEST},{NORTH},{EAST});
);
out center;"""
    request = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=urllib.parse.urlencode({"data": query}).encode(),
        headers={"User-Agent": "cawtalker-scouting/0084"})
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.load(response)
    green, water, food = [], [], []
    FOOD_TAGS = ("fast_food", "restaurant", "waste_disposal",
                 "waste_transfer_station")
    for element in payload["elements"]:
        center = element.get("center") or (
            {"lat": element.get("lat"), "lon": element.get("lon")})
        if not center.get("lat"):
            continue
        tags = element.get("tags", {})
        point = (center["lat"], center["lon"], tags.get("name", ""))
        if (tags.get("amenity") in FOOD_TAGS or tags.get("shop") == "supermarket"
                or tags.get("tourism") == "picnic_site"
                or tags.get("landuse") == "landfill"):
            food.append(point)
        elif tags.get("waterway") or tags.get("natural") == "water":
            water.append(point)
        else:
            green.append(point)
    return green, water, food


def home_center():
    import sqlite3
    db = REPO / "fieldserver" / "instance" / "field.db"
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT latitude, longitude FROM captures "
        "WHERE keep=1 AND latitude IS NOT NULL").fetchall()
    conn.close()
    if not rows:
        return None
    return (float(np.median([r[0] for r in rows])),
            float(np.median([r[1] for r in rows])))


def main():
    stands = json.load(open(
        REPO / "experiments" / "0083-where-are-the-tall-trees"
        / "tall_trees.geojson"))["features"]
    trees = [(f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0],
              f["properties"]["h"]) for f in stands]
    inat = fetch_inat()
    owls = fetch_inat("Bubo virginianus")
    hawks = fetch_inat("Accipiter cooperii") + fetch_inat("Astur cooperii")
    green, water, food = fetch_osm()
    home = home_center()
    print(f"signals: {len(inat)} iNat · {len(owls)} owls · {len(hawks)} hawks "
          f"· {len(trees)} stands · {len(green)} green · {len(water)} water "
          f"· {len(food)} food")

    nx = int((EAST - WEST) * M_PER_LON / CELL_M)
    ny = int((NORTH - SOUTH) * M_PER_LAT / CELL_M)
    lats = SOUTH + (np.arange(ny) + 0.5) * CELL_M / M_PER_LAT
    lons = WEST + (np.arange(nx) + 0.5) * CELL_M / M_PER_LON

    def kernel_layer(points, radius_m, weight=None):
        layer = np.zeros((ny, nx))
        for k, p in enumerate(points):
            plat, plon = p[0], p[1]
            w = weight(p) if weight else 1.0
            dy = (lats - plat) * M_PER_LAT
            dx = (lons - plon) * M_PER_LON
            d2 = dy[:, None] ** 2 + dx[None, :] ** 2
            layer += w * np.exp(-d2 / (2 * radius_m ** 2))
        return layer

    layers = {
        "inat": kernel_layer(inat, KERNELS_M["inat"]),
        "trees": kernel_layer(trees, KERNELS_M["trees"],
                              weight=lambda p: max(1.0, p[2] - 17)),
        "green": kernel_layer(green, KERNELS_M["green"]),
        "water": kernel_layer(water, KERNELS_M["water"]),
        "food": kernel_layer(food, KERNELS_M["food"]),
    }
    score = np.zeros((ny, nx))
    for name, layer in layers.items():
        top = np.percentile(layer, 99)
        if top > 0:
            score += WEIGHTS[name] * np.clip(layer / top, 0, 1)

    # Predators subtract after the positives sum: an owl territory can zero a
    # cell no amount of turf should rescue.
    effort = kernel_layer(fetch_inat(EFFORT_TAXON), EFFORT_KERNEL_M)
    effort_top = np.percentile(effort, 99)
    divisor = EFFORT_FLOOR + (1 - EFFORT_FLOOR) * (
        np.clip(effort / effort_top, 0, 1) if effort_top > 0 else 1)
    negatives = {"owl": kernel_layer(owls, KERNELS_M["owl"]) / divisor,
                 "hawk": kernel_layer(hawks, KERNELS_M["hawk"]) / divisor}
    for name, layer in negatives.items():
        top = np.percentile(layer, 99)
        if top > 0:
            score -= PENALTIES[name] * np.clip(layer / top, 0, 1)
    score = np.clip(score, 0, None)
    layers.update(negatives)

    if home:
        dy = (lats - home[0]) * M_PER_LAT
        dx = (lons - home[1]) * M_PER_LON
        inside = (dy[:, None] ** 2 + dx[None, :] ** 2) < HOME_EXCLUDE_M ** 2
        score[inside] = 0

    def dist2_grid(lat, lon):
        dy = (lats - lat) * M_PER_LAT
        dx = (lons - lon) * M_PER_LON
        return dy[:, None] ** 2 + dx[None, :] ** 2

    targets = []
    working = score.copy()

    def claim(j, i, district=None):
        lat, lon = float(lats[j]), float(lons[i])
        near_green = sorted(
            ((math.hypot((g[0] - lat) * M_PER_LAT, (g[1] - lon) * M_PER_LON),
              g[2]) for g in green if g[2]), key=lambda t: t[0])
        targets.append({
            "rank": len(targets) + 1, "lat": round(lat, 5),
            "lon": round(lon, 5), "score": round(float(score[j, i]), 3),
            "near": near_green[0][1] if near_green
                    and near_green[0][0] < 600 else "",
            **({"district": district} if district else {}),
            "signals": {k: round(float(np.clip(
                layers[k][j, i] / (np.percentile(layers[k], 99) or 1), 0, 1)), 2)
                for k in layers},
        })
        working[dist2_grid(lat, lon) < SEPARATION_M ** 2] = 0

    while len(targets) < N_TARGETS and working.max() > 0:
        j, i = np.unravel_index(np.argmax(working), working.shape)
        claim(j, i)

    for name, dlat, dlon in DISTRICTS:
        if any(math.hypot((t["lat"] - dlat) * M_PER_LAT,
                          (t["lon"] - dlon) * M_PER_LON) < DISTRICT_RADIUS_M
               for t in targets):
            continue
        masked = np.where(dist2_grid(dlat, dlon) < DISTRICT_RADIUS_M ** 2,
                          working, 0)
        if masked.max() <= 0:
            continue
        j, i = np.unravel_index(np.argmax(masked), masked.shape)
        claim(j, i, district=name)

    (OUT / "targets.json").write_text(json.dumps(targets, indent=2) + "\n")
    for t in targets[:10]:
        label = f" ({t['near']})" if t["near"] else ""
        print(f"#{t['rank']:2d} score {t['score']} at "
              f"{t['lat']},{t['lon']}{label} {t['signals']}")

    owl_points = [{"lat": round(o[0], 5), "lon": round(o[1], 5)}
                  for o in owls]
    # Merge, never rewrite: build_predators.py parks the per-species sighting
    # list and the inline icons in the same file, and a plain dump here would
    # silently strip them from the next publish.
    layer_path = OUT / "scout_layer.json"
    layer = json.loads(layer_path.read_text()) if layer_path.exists() else {}
    layer.update({"targets": targets, "owls": owl_points})
    layer_path.write_text(json.dumps(layer) + "\n")
    html = (OUT / "map_template.html").read_text().replace(
        "__TARGETS__", json.dumps(targets)).replace(
        "__OWLS__", json.dumps(owl_points))
    (OUT / "scout-map.html").write_text(html)
    print(f"wrote {len(targets)} targets -> scout-map.html")


if __name__ == "__main__":
    main()
