"""Can the photo model tell when it is not looking at a corvid?

A visitor uploaded a black cat and the Scan page named it a Fish Crow. The
head only knows nine corvids, so it always names one. This measures four
signals that could say "not a corvid" instead:

  - the head's own top probability, from pixels alone (the first idea:
    below some percent, refuse to name anything);
  - whether the detector found a bird at all;
  - how close the photo's BioCLIP embedding sits to the corvid photos the
    model was trained on (nearest species centroid, and nearest neighbours);
  - both embedding signals again on the bird crop.

Corvids are the training photos, scored out of fold so no photo vouches for
itself, and the corvids among the scout layer's archived sighting photos,
which the model has never seen. Non-corvids are that archive's hawks, owls
and falcons: birds, so the hard case, since a cat fails the detector too.
It also reports how the production model does on the archive's corvids,
the first photos from outside the training source.

    analyzer/photo/.venv/bin/python experiments/0094-can-the-photo-model-say-not-a-corvid/run.py
"""

import csv
import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from analyzer.photo.identify import PhotoIdentifier  # noqa: E402
from analyzer.photo.train import BOXES, FEATURES, FOLDS, BoxCache, FeatureCache, TrainingPhoto, new_classifier  # noqa: E402
from analyzer.photo.vision import open_photo  # noqa: E402
from crowgpt.progress import Run  # noqa: E402

DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
INSTANCE = REPO / "fieldserver" / "instance"
SCOUT_CACHE = DATA / "photos" / "embeddings" / "scout-sightings.npz"
CORVIDS = {"American Crow": "american-crow", "Common Raven": "common-raven", "Black-billed Magpie": "black-billed-magpie"}
NEIGHBOURS = 5
MISS_RATES = (0.01, 0.02, 0.05, 0.10)


class Sighting:
    def __init__(self, record):
        self.species = record["species"]
        self.latitude = record["lat"]
        self.longitude = record["lon"]
        name = record["photo"].split("/photos/")[-1].split("/")[0]
        suffix = Path(record["photo"].split("?")[0]).suffix or ".jpg"
        self.key = name
        self.path = INSTANCE / "scout-photos" / f"{name}{suffix}"

    @property
    def is_corvid(self):
        return self.species in CORVIDS

    @classmethod
    def load_all(cls):
        layer = json.loads((INSTANCE / "scout.json").read_text())
        seen, sightings = set(), []
        for record in layer.get("predators", []):
            if not record.get("photo"):
                continue
            sighting = cls(record)
            if sighting.path.exists() and sighting.key not in seen:
                seen.add(sighting.key)
                sightings.append(sighting)
        return sightings


class SightingFeatures:
    """The production pipeline's vector and box for each archived photo."""

    def __init__(self, path):
        self.path = path
        self.vectors, self.found = {}, {}
        if path.exists():
            stored = np.load(path)
            self.vectors = dict(zip(stored["key"].tolist(), stored["vectors"]))
            self.found = dict(zip(stored["key"].tolist(), stored["found"].tolist()))

    def fill(self, sightings, identifier, stage):
        todo = [s for s in sightings if s.key not in self.vectors]
        for count, sighting in enumerate(todo, 1):
            vector, look = identifier.features.extract(open_photo(sighting.path))
            self.vectors[sighting.key], self.found[sighting.key] = vector, look.box is not None
            if count % 25 == 0 or count == len(todo):
                self.save()
                stage.update(count, len(todo), extra=sighting.species)
        stage.update(len(todo), len(todo))

    def save(self):
        keys = list(self.vectors)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.path, key=np.array(keys), vectors=np.stack([self.vectors[k] for k in keys]),
                 found=np.array([self.found[k] for k in keys]))


class Familiarity:
    """How close a vector sits to a reference set of corvid vectors."""

    def __init__(self, vectors, labels):
        self.vectors = self._unit(vectors)
        self.centroids = self._unit(np.stack([vectors[labels == k].mean(axis=0) for k in np.unique(labels)]))

    @staticmethod
    def _unit(matrix):
        return matrix / np.linalg.norm(matrix, axis=1, keepdims=True)

    def centroid(self, queries):
        return (self._unit(queries) @ self.centroids.T).max(axis=1)

    def neighbours(self, queries):
        similarity = self._unit(queries) @ self.vectors.T
        return np.sort(similarity, axis=1)[:, -NEIGHBOURS:].mean(axis=1)


class Signals:
    """Every candidate signal for one group of photos, higher meaning more
    corvid-like."""

    def __init__(self, top_probability, bird_found, vectors, whole, crop):
        half = vectors.shape[1] // 2
        self.values = {
            "top probability": top_probability,
            "bird found": bird_found.astype(float),
            "whole: centroid": whole.centroid(vectors[:, :half]),
            "whole: neighbours": whole.neighbours(vectors[:, :half]),
            "crop: centroid": crop.centroid(vectors[:, half:]),
            "crop: neighbours": crop.neighbours(vectors[:, half:]),
        }

    @classmethod
    def join(cls, parts):
        joined = cls.__new__(cls)
        joined.values = {name: np.concatenate([p.values[name] for p in parts]) for name in parts[0].values}
        return joined


def out_of_fold(vectors, labels, found):
    half = vectors.shape[1] // 2
    parts = []
    for train, test in StratifiedKFold(n_splits=FOLDS, shuffle=True, random_state=0).split(vectors, labels):
        head = new_classifier().fit(vectors[train], labels[train])
        parts.append(Signals(
            head.predict_proba(vectors[test]).max(axis=1), found[test], vectors[test],
            Familiarity(vectors[train][:, :half], labels[train]), Familiarity(vectors[train][:, half:], labels[train])))
    return Signals.join(parts)


class Separation:
    def __init__(self, corvids, others):
        self.corvids = corvids
        self.others = others

    def table(self, title):
        lines = [f"## {title}: {len(next(iter(self.corvids.values.values())))} corvids, "
                 f"{len(next(iter(self.others.values.values())))} non-corvids",
                 f"  {'signal':20s}{'AUC':>7s}" + "".join(f"{'lose ' + format(m, '.0%'):>10s}" for m in MISS_RATES),
                 f"  {'':20s}{'':>7s}" + "".join(f"{'corvids':>10s}" for _ in MISS_RATES)]
        for name in self.corvids.values:
            yes, no = self.corvids.values[name], self.others.values[name]
            auc = roc_auc_score(np.r_[np.ones(len(yes)), np.zeros(len(no))], np.r_[yes, no])
            if name == "bird found":
                lines.append(f"  {name:20s}{auc:7.3f}   loses {1 - yes.mean():.1%} of corvids, catches {1 - no.mean():.1%} of non-corvids")
                continue
            caught = [np.mean(no < np.quantile(yes, miss)) for miss in MISS_RATES]
            lines.append(f"  {name:20s}{auc:7.3f}" + "".join(f"{c:10.1%}" for c in caught))
        return "\n".join(lines)


def archive_accuracy(identifier, sightings, features):
    corvids = [s for s in sightings if s.is_corvid]
    classes = identifier.head.classes
    vectors = np.stack([features.vectors[s.key] for s in corvids])
    image = identifier.head.log_probabilities(vectors)
    located = image + np.array([identifier.atlas.log_likelihoods(classes, s.latitude, s.longitude) for s in corvids])
    lines = [f"## the production model on the archive's {len(corvids)} corvids (never seen, small thumbnails)"]
    for label, scores in (("pixels", image), ("pixels + location", located)):
        guesses = [classes[i] for i in scores.argmax(axis=1)]
        per = []
        for species, slug in CORVIDS.items():
            mine = [g for g, s in zip(guesses, corvids) if s.species == species]
            wrong = Counter(g for g in mine if g != slug).most_common(2)
            per.append(f"{species} {np.mean([g == slug for g in mine]):.1%} of {len(mine)} "
                       f"(wrong: {', '.join(f'{w} {n}' for w, n in wrong) or '-'})")
        lines.append(f"  {label:18s} " + "; ".join(per))
    return "\n".join(lines)


def main():
    run = Run("0094 — NOT A CORVID", ["embed the archive", "score"])
    identifier = PhotoIdentifier.load()
    sightings = Sighting.load_all()
    features = SightingFeatures(SCOUT_CACHE)
    with run.stage("embed the archive") as stage:
        features.fill(sightings, identifier, stage)
    with run.stage("score") as stage:
        photos = TrainingPhoto.load_all()
        classes = sorted({p.slug for p in photos})
        vectors = FeatureCache(FEATURES).matrix(photos)
        labels = np.array([classes.index(p.slug) for p in photos])
        boxes = BoxCache(BOXES)
        found = np.array([boxes.box(p) is not None for p in photos])
        half = vectors.shape[1] // 2
        training = out_of_fold(vectors, labels, found)
        whole, crop = Familiarity(vectors[:, :half], labels), Familiarity(vectors[:, half:], labels)

        def archive(group):
            matrix = np.stack([features.vectors[s.key] for s in group])
            top = np.exp(identifier.head.log_probabilities(matrix)).max(axis=1)
            return Signals(top, np.array([features.found[s.key] for s in group]), matrix, whole, crop)

        others = [s for s in sightings if not s.is_corvid]
        seen_corvids = [s for s in sightings if s.is_corvid]
        report = "\n\n".join([
            f"archive: {dict(Counter(s.species for s in sightings))}",
            Separation(training, archive(others)).table("training corvids (out of fold) against the archive's raptors and owls"),
            Separation(archive(seen_corvids), archive(others)).table("the archive's own corvids against its raptors and owls"),
            archive_accuracy(identifier, sightings, features),
        ])
        print(report)
        run.note(report)
        stage.update(1, 1)


if __name__ == "__main__":
    main()
