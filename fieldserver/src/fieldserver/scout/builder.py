"""Assemble the full scout layer: targets, owls, predators, icons, rail.

One builder call replaces the 0084 script chain (run.py + build_predators.py
+ build_rail.py + publish_scout.py). Regions concatenate: ranks continue
across them so every pin number on the map stays unique.
"""

import base64
import io
import json
import sqlite3
from pathlib import Path

import numpy as np

from .regions import REGIONS
from .scoring import EFFORT_TAXON, RegionScorer
from .sources import INatClient, OverpassClient

CROW_TAXON = "Corvus brachyrhynchos"
OWL_TAXON = "Bubo virginianus"
HAWK_TAXA = ("Accipiter cooperii", "Astur cooperii")

#: species -> map icon. Icon None would mean a purple dot; everything here
#: has one of Ben's drawings. Kestrels were removed 2026-08-20 on his call —
#: a 110 g vole-falcon threatens no crow.
PREDATOR_SPECIES = {
    "Bubo virginianus": ("owl-icon", "Great Horned Owl"),
    "Megascops kennicottii": ("owl-icon", "Western Screech-Owl"),
    "Buteo jamaicensis": ("hawk-icon", "Red-tailed Hawk"),
    "Falco peregrinus": ("peregrine-icon", "Peregrine Falcon"),
    # Cooper's rides under two taxon names (iNat's Accipiter -> Astur move)
    # and both return the same observations; the dedupe below folds them.
    "Accipiter cooperii": ("coopers-hawk-icon", "Cooper's Hawk"),
    "Astur cooperii": ("coopers-hawk-icon", "Cooper's Hawk"),
    # Ravens raid crow nests and get mobbed; magpies threaten nobody but
    # mark good corvid habitat.
    "Corvus corax": ("raven-icon", "Common Raven"),
    "Pica hudsonia": ("magpie-icon", "Black-billed Magpie"),
}
ICON_STYLE = "detailed full-body"

#: eBird species code -> (display species, icon, community). Fresh sightings
#: from the last 30 days ride the same predators list as iNat's history,
#: tagged src="ebird" and by="eBird".
EBIRD_SPECIES = {
    "amecro": ("American Crow", "crow-icon", True),
    "grhowl": ("Great Horned Owl", "owl-icon", False),
    "wesowl1": ("Western Screech-Owl", "owl-icon", False),
    "rethaw": ("Red-tailed Hawk", "hawk-icon", False),
    "coohaw": ("Cooper's Hawk", "coopers-hawk-icon", False),
    "perfal": ("Peregrine Falcon", "peregrine-icon", False),
    "comrav": ("Common Raven", "raven-icon", False),
    "bkbmag1": ("Black-billed Magpie", "magpie-icon", False),
}


class ScoutLayerBuilder:
    def __init__(self, repo_root, db_path=None, inat=None, overpass=None,
                 ebird=None, grid_dir=None, log=print):
        self.repo_root = Path(repo_root)
        self.db_path = db_path
        self.inat = inat or INatClient()
        self.overpass = overpass or OverpassClient()
        self.ebird = ebird
        self.grid_dir = grid_dir
        self.log = log

    def build(self, regions=None, previous=None):
        regions = regions or REGIONS
        previous = previous or {}
        home = self._home_center()
        # Every row carries its region so the map's county filter can thin
        # the layer without guessing from coordinates.
        layer = {"regions": [{"slug": r.slug, "name": r.name} for r in regions],
                 "targets": [], "owls": [], "predators": [], "rail": []}
        for region in regions:
            self._add_region(layer, region, home)
        layer["icons"] = self._icons(
            {p["icon"] for p in layer["predators"]},
            previous.get("icons", {}))
        return layer

    def _add_region(self, layer, region, home):
        trees = self._load_trees(region)
        inat = self.inat.presence_points(CROW_TAXON, region)
        owls = self.inat.presence_points(OWL_TAXON, region)
        hawks = [p for taxon in HAWK_TAXA
                 for p in self.inat.presence_points(taxon, region)]
        effort = self.inat.presence_points(EFFORT_TAXON, region)
        green, water, food = self.overpass.habitat(region)
        self.log(f"[{region.slug}] signals: {len(inat)} iNat · {len(owls)} owls"
                 f" · {len(hawks)} hawks · {len(trees)} stands"
                 f" · {len(green)} green · {len(water)} water"
                 f" · {len(food)} food")

        scorer = RegionScorer(region, inat=inat, trees=trees, green=green,
                              water=water, food=food, owls=owls, hawks=hawks,
                              effort=effort, home=home)
        self._save_grid(region, scorer, green)
        offset = len(layer["targets"])
        for target in scorer.targets():
            target["rank"] += offset
            layer["targets"].append(target)
        layer["owls"] += [{"lat": round(o[0], 5), "lon": round(o[1], 5),
                           "region": region.slug} for o in owls]
        layer["predators"] += [{**p, "region": region.slug}
                               for p in self._predators(region)]
        layer["rail"] += [{**seg, "region": region.slug}
                          for seg in self.overpass.rail(region)]

    def _save_grid(self, region, scorer, green):
        """The scored surface, persisted beside the layer so /api/scout/spots
        can answer 'best cells inside this circle' without refetching a
        single signal. Named greens ride along for the 'near' labels."""
        if not self.grid_dir:
            return
        named = [g for g in green if g[2]]
        grid_dir = Path(self.grid_dir)
        grid_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            grid_dir / f"{region.slug}.npz",
            green_lat=np.array([g[0] for g in named], dtype=float),
            green_lon=np.array([g[1] for g in named], dtype=float),
            green_name=np.array([g[2] for g in named], dtype=str),
            **scorer.grid())

    def _predators(self, region):
        points = []
        for taxon, (icon, common) in PREDATOR_SPECIES.items():
            for obs in self.inat.recent(taxon, region):
                points.append({"lat": obs.lat, "lon": obs.lon, "icon": icon,
                               "species": common, "style": ICON_STYLE,
                               "date": obs.date, "photo": obs.photo,
                               "by": obs.observer})
        # Community crow sightings ride the same list, flagged so the map can
        # say plainly "someone else's crow" — Ben's own captures stay the
        # full-colour markers with family glows.
        for obs in self.inat.recent(CROW_TAXON, region):
            points.append({"lat": obs.lat, "lon": obs.lon, "icon": "crow-icon",
                           "species": "American Crow", "community": True,
                           "date": obs.date, "photo": obs.photo,
                           "by": obs.observer})
        if self.ebird:
            for code, (common, icon, community) in EBIRD_SPECIES.items():
                for obs in self.ebird.recent(code, region):
                    points.append({
                        "lat": obs["lat"], "lon": obs["lon"], "icon": icon,
                        "species": common, "src": "ebird", "date": obs["date"],
                        "count": obs["count"], "by": "eBird", "photo": "",
                        **({"community": True} if community else {})})
        else:
            self.log(f"[{region.slug}] no eBird client — "
                     f"fresh sightings skipped")
        seen, unique = set(), []
        for p in points:
            key = (p["species"], p["lat"], p["lon"])
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique

    def _icons(self, wanted, cached):
        """Data-URIs riding inside the layer, so an icon change is a
        republish, never an app build. Carried forward from the previous
        publish; only a genuinely new name rasterises a master from
        images/, which is the one path that needs Pillow."""
        icons = {}
        for name in sorted(wanted | {"crow-icon"}):
            icons[name] = cached.get(name) or self._rasterize(name)
        return icons

    def _rasterize(self, name):
        from PIL import Image
        master = self.repo_root / "images" / f"{name}.png"
        if not master.exists():
            raise FileNotFoundError(
                f"no icon master {master} and no cached data-URI — "
                f"draw one or publish once with the icon already in the layer")
        buf = io.BytesIO()
        Image.open(master).resize((64, 64), Image.LANCZOS).save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    def _home_center(self):
        if not self.db_path or not Path(self.db_path).exists():
            return None
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT latitude, longitude FROM captures "
            "WHERE keep=1 AND latitude IS NOT NULL").fetchall()
        conn.close()
        if not rows:
            return None
        return (float(np.median([r[0] for r in rows])),
                float(np.median([r[1] for r in rows])))

    def _load_trees(self, region):
        path = self.repo_root / region.trees_geojson
        if not path.exists():
            raise FileNotFoundError(
                f"[{region.slug}] no tall-trees layer at {path} — "
                f"trees lead the weights, so a region without canopy data "
                f"cannot be scored (see experiments/0083 for how to build it)")
        features = json.loads(path.read_text())["features"]
        return [(f["geometry"]["coordinates"][1],
                 f["geometry"]["coordinates"][0],
                 f["properties"]["h"]) for f in features]


def validate(layer):
    """The shape the app depends on — ranked targets with coordinates and a
    score, owl points with coordinates, unique pin numbers."""
    targets = layer.get("targets")
    if not targets:
        raise ValueError("no targets in layer")
    for t in targets:
        for key in ("rank", "lat", "lon", "score"):
            if not isinstance(t.get(key), (int, float)):
                raise ValueError(f"target missing numeric `{key}`: {t}")
    ranks = [t["rank"] for t in targets]
    if len(set(ranks)) != len(ranks):
        raise ValueError("duplicate target ranks — pin numbers must be unique")
    for o in layer.get("owls", [])[:50]:
        if not isinstance(o.get("lat"), (int, float)):
            raise ValueError(f"owl missing `lat`: {o}")
    for p in layer.get("predators", []):
        if p["icon"] and p["icon"] not in layer.get("icons", {}):
            raise ValueError(f"predator icon `{p['icon']}` not in icons")
