"""Where each species gets documented, and how likely a place is for each.

Built from Macaulay Library CSV exports: every located row (photo, audio or
video) is a point where that species was recorded. A place's likelihood for a
species is the share of that species' records within a radius of it. numpy
only, so it loads and tests without a model.

Experiment 0091 measured this: it lifts nine-species accuracy from 78% to 90%,
and the radius barely matters between 50 and 500 km.
"""

import csv
import re
from pathlib import Path

import numpy as np

EARTH_KM = 6371.0
RADIUS_KM = 150
#: Added to every share so a species with no record nearby is unlikely, not
#: impossible. The same for every species: a count-based smoothing would favour
#: whichever species has the fewest records wherever none has any.
FLOOR = 5e-5


def slugify(common_name: str) -> str:
    species = re.sub(r"\s*\(.*\)", "", common_name)
    return re.sub(r"[^a-z0-9]+", "-", species.lower()).strip("-")


class Occurrences:
    def __init__(self, positions, recordists=None):
        self.positions = np.asarray(positions, dtype=np.float64).reshape(-1, 2)
        self.recordists = recordists

    @classmethod
    def from_degrees(cls, coordinates, recordists=None):
        return cls(np.radians(np.asarray(coordinates, dtype=np.float64).reshape(-1, 2)), recordists)

    def share_within(self, latitude, longitude, radius_km=RADIUS_KM, excluding_recordist=None):
        """The share of this species' records within the radius. Naming a
        recordist leaves their records out, which validation uses so a
        photographer's other uploads cannot vouch for their own photo."""
        near = self._distance_km(np.radians([latitude, longitude])) <= radius_km
        if excluding_recordist is None or self.recordists is None:
            return float(near.mean()) if len(near) else 0.0
        others = self.recordists != excluding_recordist
        return float(np.sum(near & others) / max(np.sum(others), 1))

    def _distance_km(self, position):
        dlat = self.positions[:, 0] - position[0]
        dlon = self.positions[:, 1] - position[1]
        a = np.sin(dlat / 2) ** 2 + np.cos(position[0]) * np.cos(self.positions[:, 0]) * np.sin(dlon / 2) ** 2
        return 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


class Atlas:
    def __init__(self, species: dict, names: dict):
        self.species = species
        self.names = names

    @classmethod
    def from_exports(cls, exports_dir: Path):
        coordinates, recordists, names = {}, {}, {}
        for path in sorted(Path(exports_dir).glob("*.csv")):
            with open(path, newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    if not (row["Latitude"] and row["Longitude"]):
                        continue
                    slug = slugify(row["Common Name"])
                    coordinates.setdefault(slug, []).append((float(row["Latitude"]), float(row["Longitude"])))
                    recordists.setdefault(slug, []).append(row["Recordist"])
                    names.setdefault(slug, {
                        "common": re.sub(r"\s*\(.*\)", "", row["Common Name"]),
                        "scientific": row.get("Parent Species") or row["Scientific Name"],
                    })
        species = {slug: Occurrences.from_degrees(points, np.array(recordists[slug]))
                   for slug, points in coordinates.items()}
        return cls(species, names)

    def save(self, path: Path):
        """Positions and names only. Recordists stay behind: they are needed
        to validate, not to identify, and are not this file's to pass on."""
        slugs = sorted(self.species)
        np.savez_compressed(
            path,
            slugs=np.array(slugs),
            common=np.array([self.names[s]["common"] for s in slugs]),
            scientific=np.array([self.names[s]["scientific"] for s in slugs]),
            counts=np.array([len(self.species[s].positions) for s in slugs]),
            positions=np.concatenate([self.species[s].positions for s in slugs]).astype(np.float32),
        )

    @classmethod
    def load(cls, path: Path):
        stored = np.load(path)
        bounds = np.concatenate([[0], np.cumsum(stored["counts"])])
        species, names = {}, {}
        for index, slug in enumerate(stored["slugs"].tolist()):
            species[slug] = Occurrences(stored["positions"][bounds[index]:bounds[index + 1]])
            names[slug] = {"common": str(stored["common"][index]), "scientific": str(stored["scientific"][index])}
        return cls(species, names)

    def shares(self, classes, latitude, longitude, excluding_recordist=None):
        return np.array([
            self.species[c].share_within(latitude, longitude, excluding_recordist=excluding_recordist)
            for c in classes
        ])

    def log_likelihoods(self, classes, latitude, longitude, excluding_recordist=None):
        return np.log(self.shares(classes, latitude, longitude, excluding_recordist) + FLOOR)

    def knows(self, classes, latitude, longitude) -> bool:
        """False where no candidate has a record nearby, so the place says
        nothing and the photo should be judged by pixels alone."""
        return bool(self.shares(classes, latitude, longitude).any())
