"""The scouting score: a weighted prior over a 250 m grid, per region.

Ported intact from experiment 0084 (see its README for the field validation
that earned each term). This is a heuristic, not a fitted model — its
validation is field trips, and every visit mark is a label the weights can
later be checked against.
"""

import math

import numpy as np

CELL_M = 250
HOME_EXCLUDE_M = 800
DISTRICT_RADIUS_M = 1500
M_PER_LAT = 110_540

# Trees lead, crow reports second: canopy is the one signal measured
# uniformly everywhere (satellite), while iNat reports carry a measured 2:1
# east/west observer-effort skew in the valley — the biased instrument
# should not be the loudest.
WEIGHTS = {"inat": 0.25, "trees": 0.32, "green": 0.17, "water": 0.12,
           "food": 0.14}
PENALTIES = {"owl": 0.30, "hawk": 0.08}
KERNELS_M = {"inat": 600, "trees": 400, "green": 400, "water": 500,
             "food": 500, "owl": 500, "hawk": 400}
# Predator reports are deflated by local birding effort (robin observations
# as the proxy): twice the eyes report twice the owls, and without this the
# penalty falls hardest on the best-watched ground. Floor 0.3 so unbirded
# areas don't explode the division.
EFFORT_TAXON = "Turdus migratorius"
EFFORT_KERNEL_M = 800
EFFORT_FLOOR = 0.3
# Nest stands only start counting above 17 m, then linearly by height.
TREE_BASE_M = 17


class RegionScorer:
    """Grids one region's signals, applies the weights, picks the targets.

    Pure given its inputs — every point list arrives fetched, so tests run
    on synthetic geography.
    """

    def __init__(self, region, *, inat, trees, green, water, food,
                 owls, hawks, effort, home=None):
        self.region = region
        self.green = green
        self.home = home
        self.m_per_lon = 111_320 * math.cos(
            math.radians((region.south + region.north) / 2))
        nx = int((region.east - region.west) * self.m_per_lon / CELL_M)
        ny = int((region.north - region.south) * M_PER_LAT / CELL_M)
        self.lats = region.south + (np.arange(ny) + 0.5) * CELL_M / M_PER_LAT
        self.lons = region.west + (np.arange(nx) + 0.5) * CELL_M / self.m_per_lon
        self.layers = {
            "inat": self._kernel(inat, KERNELS_M["inat"]),
            "trees": self._kernel(trees, KERNELS_M["trees"],
                                  weight=lambda p: max(1.0, p[2] - TREE_BASE_M)),
            "green": self._kernel(green, KERNELS_M["green"]),
            "water": self._kernel(water, KERNELS_M["water"]),
            "food": self._kernel(food, KERNELS_M["food"]),
        }
        self.score = np.zeros_like(self.layers["inat"])
        for name, layer in self.layers.items():
            self.score += WEIGHTS[name] * self._normalized(layer)

        # Predators subtract after the positives sum: an owl territory can
        # zero a cell no amount of turf should rescue.
        effort_layer = self._normalized(self._kernel(effort, EFFORT_KERNEL_M))
        divisor = EFFORT_FLOOR + (1 - EFFORT_FLOOR) * effort_layer
        negatives = {"owl": self._kernel(owls, KERNELS_M["owl"]) / divisor,
                     "hawk": self._kernel(hawks, KERNELS_M["hawk"]) / divisor}
        for name, layer in negatives.items():
            self.score -= PENALTIES[name] * self._normalized(layer)
        self.score = np.clip(self.score, 0, None)
        self.layers.update(negatives)

        # The point is NEW families — the home territory is excluded.
        if home and region.contains(*home):
            self.score[self._dist2(*home) < HOME_EXCLUDE_M ** 2] = 0

    def _kernel(self, points, radius_m, weight=None):
        layer = np.zeros((len(self.lats), len(self.lons)))
        for p in points:
            w = weight(p) if weight else 1.0
            dy = (self.lats - p[0]) * M_PER_LAT
            dx = (self.lons - p[1]) * self.m_per_lon
            layer += w * np.exp(-(dy[:, None] ** 2 + dx[None, :] ** 2)
                                / (2 * radius_m ** 2))
        return layer

    @staticmethod
    def _normalized(layer):
        top = np.percentile(layer, 99)
        return np.clip(layer / top, 0, 1) if top > 0 else layer

    def _dist2(self, lat, lon):
        dy = (self.lats - lat) * M_PER_LAT
        dx = (self.lons - lon) * self.m_per_lon
        return dy[:, None] ** 2 + dx[None, :] ** 2

    def grid(self):
        """The whole scored surface, keyed for np.savez — what a later
        circle-query needs. The build pipeline keeps only the top pins;
        persisting this is what makes 'best spots inside MY circle' a
        lookup instead of a rebuild."""
        data = {"lats": self.lats, "lons": self.lons, "score": self.score}
        for name, layer in self.layers.items():
            data["sig_" + name] = self._normalized(layer)
        return data

    def targets(self):
        """Ranked targets: the open field first (greedy, separated so twenty
        targets are twenty places), then a floor pin for any district the
        open ranking left empty — a target list Ben won't drive to predicts
        nothing."""
        picked = []
        working = self.score.copy()

        def claim(j, i, district=None):
            lat, lon = float(self.lats[j]), float(self.lons[i])
            near = sorted(
                ((math.hypot((g[0] - lat) * M_PER_LAT,
                             (g[1] - lon) * self.m_per_lon), g[2])
                 for g in self.green if g[2]), key=lambda t: t[0])
            picked.append({
                "rank": len(picked) + 1,
                "lat": round(lat, 5), "lon": round(lon, 5),
                "score": round(float(self.score[j, i]), 3),
                "near": near[0][1] if near and near[0][0] < 600 else "",
                "region": self.region.slug,
                **({"district": district} if district else {}),
                "signals": {name: round(float(self._normalized(layer)[j, i]), 2)
                            for name, layer in self.layers.items()},
            })
            working[self._dist2(lat, lon) < self.region.separation_m ** 2] = 0

        while len(picked) < self.region.n_targets and working.max() > 0:
            claim(*np.unravel_index(np.argmax(working), working.shape))

        for name, dlat, dlon in self.region.districts:
            if any(math.hypot((t["lat"] - dlat) * M_PER_LAT,
                              (t["lon"] - dlon) * self.m_per_lon)
                   < DISTRICT_RADIUS_M for t in picked):
                continue
            masked = np.where(self._dist2(dlat, dlon) < DISTRICT_RADIUS_M ** 2,
                              working, 0)
            if masked.max() <= 0:
                continue
            claim(*np.unravel_index(np.argmax(masked), masked.shape),
                  district=name)
        return picked
