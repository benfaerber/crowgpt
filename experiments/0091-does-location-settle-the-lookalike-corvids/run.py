"""Does knowing where a photo was taken settle the look-alike corvids?

0090 left Common vs Chihuahuan Raven near 70% from pixels alone. This adds a
location term built in house from the Macaulay CSV exports: every located
record in an export (photo, audio or video) is a point where that species was
documented, and a photo's location likelihood for a species is the share of
that species' records within a radius of it. Records by the photo's own
recordist are left out, so a photographer's other uploads from the same spot
cannot vouch for their own photo.

Scores three ways per species: image head alone (5-fold CV probabilities on
0090's cached BioCLIP 2 embeddings), location alone, and the product.
Run 0090 first; it fills the embedding cache.

    uv run --with numpy --with scikit-learn \\
        python experiments/0091-does-location-settle-the-lookalike-corvids/run.py
"""

import csv
import os
import re
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
PHOTOS = DATA / "photos"
CACHE = PHOTOS / "embeddings" / "bioclip-2.npz"
EXPORTS = PHOTOS / "macaulay-exports"
RADII_KM = (50, 150, 500)
EARTH_KM = 6371.0


def slugify(common_name):
    species = re.sub(r"\s*\(.*\)", "", common_name)
    return re.sub(r"[^a-z0-9]+", "-", species.lower()).strip("-")


class Photo:
    def __init__(self, row, vector):
        self.slug = row["slug"]
        self.recordist = row["recordist"]
        self.position = np.radians([float(row["latitude"]), float(row["longitude"])])
        self.vector = vector


class Occurrences:
    """Every located record of one species across the exports."""

    def __init__(self, slug, rows):
        self.slug = slug
        self.positions = np.radians([[float(r["Latitude"]), float(r["Longitude"])] for r in rows])
        self.recordists = np.array([r["Recordist"] for r in rows])
        self.records_per_day = self._records_per_day(rows)

    @staticmethod
    def _records_per_day(rows):
        """How fast this species is documented, from the newer half of its
        records. An export is capped at 10,000 rows, so the row count says
        nothing about abundance; how little time the cap spans does."""
        days = sorted(date.fromisoformat(r["Date"]).toordinal() for r in rows if r["Date"])
        return (len(days) / 2) / (days[-1] - days[len(days) // 2] + 1)

    def share_within(self, photo, radius_km):
        """Smoothed share of this species' records, not by the photo's own
        recordist, that fall within the radius of the photo."""
        others = self.recordists != photo.recordist
        near = self._distance_km(photo.position) <= radius_km
        return (np.sum(near & others) + 0.5) / (np.sum(others) + 1.0)

    def _distance_km(self, position):
        dlat = self.positions[:, 0] - position[0]
        dlon = self.positions[:, 1] - position[1]
        a = np.sin(dlat / 2) ** 2 + np.cos(position[0]) * np.cos(self.positions[:, 0]) * np.sin(dlon / 2) ** 2
        return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


class Atlas:
    def __init__(self, exports_dir):
        by_slug = {}
        for path in sorted(exports_dir.glob("*.csv")):
            with open(path, newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    if row["Latitude"] and row["Longitude"]:
                        by_slug.setdefault(slugify(row["Common Name"]), []).append(row)
        self.species = {slug: Occurrences(slug, rows) for slug, rows in by_slug.items()}

    def log_likelihoods(self, photos, classes, radius_km):
        return np.log([[self.species[c].share_within(p, radius_km) for c in classes] for p in photos])

    def log_record_rates(self, classes):
        return np.log([self.species[c].records_per_day for c in classes])


class Comparison:
    def __init__(self, photos, classes):
        self.photos = photos
        self.classes = classes
        self.labels = np.array([classes.index(p.slug) for p in photos])

    def image_log_probabilities(self):
        head = LogisticRegression(max_iter=2000, class_weight="balanced")
        folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
        vectors = np.stack([p.vector for p in self.photos])
        return np.log(cross_val_predict(head, vectors, self.labels, cv=folds, method="predict_proba"))

    def report(self, title, scores):
        guesses = scores.argmax(axis=1)
        lines = [f"## {title}"]
        recalls = []
        for index, slug in enumerate(self.classes):
            rows = self.labels == index
            counts = Counter(self.classes[g] for g in guesses[rows])
            recalls.append(counts[slug] / rows.sum())
            wrong = ", ".join(f"{s} {n}" for s, n in counts.most_common(4) if s != slug)
            lines.append(f"  {slug:22s} n={rows.sum():4d}  top-1 {recalls[-1]:6.1%}  wrong: {wrong or '-'}")
        lines.append(f"  balanced accuracy {np.mean(recalls):6.1%}")
        return "\n".join(lines)


def load_photos():
    stored = np.load(CACHE)
    vectors = dict(zip(stored["sha1"], stored["vectors"]))
    with open(PHOTOS / "manifest.csv", newline="") as handle:
        return [Photo(row, vectors[row["sha1"]]) for row in csv.DictReader(handle)
                if row["latitude"] and row["longitude"] and row["sha1"] in vectors]


def main():
    photos = load_photos()
    classes = sorted({p.slug for p in photos})
    atlas = Atlas(EXPORTS)
    comparison = Comparison(photos, classes)
    image = comparison.image_log_probabilities()
    rates = atlas.log_record_rates(classes)
    print("records per day: " + ", ".join(f"{c} {np.exp(r):.1f}" for c, r in zip(classes, rates)))
    print()
    print(comparison.report(f"image head alone: {len(classes)} species", image))
    for radius in RADII_KM:
        location = atlas.log_likelihoods(photos, classes, radius)
        print()
        print(comparison.report(f"location alone, {radius} km", location))
        print()
        print(comparison.report(f"image head x location, {radius} km", image + location))
        print()
        print(comparison.report(f"image head x location x record rate, {radius} km", image + location + rates))


if __name__ == "__main__":
    main()
