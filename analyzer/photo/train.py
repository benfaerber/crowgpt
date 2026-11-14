"""Train the photo classifier from data/photos and write it where it is read.

    make photos        # the photos, from the Macaulay CSV exports
    make photo-train   # this

Detects the bird in every 1200px photo, embeds whole frame and crop, measures
the head by 5-fold cross-validation with and without the location term, then
fits on everything and writes head.joblib, atlas.npz and metrics.json to the
model directory. Boxes and features are cached under data/photos, so a re-run
after adding a species only processes the new photos.
"""

import csv
import json
import multiprocessing
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from .atlas import RADIUS_KM, Atlas
from .identify import ATLAS_FILE, HEAD_FILE, REPO, SpeciesHead, default_model_dir
from .vision import BIOCLIP, BioclipEmbedder, BirdBox, BirdDetector, PhotoFeatures, open_photo

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
PHOTOS = DATA / "photos"
BOXES = PHOTOS / "boxes" / "fasterrcnn-resnet50-fpn-v2.json"
FEATURES = PHOTOS / "embeddings" / "photo-id-whole-crop.npz"
DETECT_WORKERS = 4
EMBED_THREADS = 16
BATCH = 16
FOLDS = 5


class TrainingPhoto:
    def __init__(self, row):
        self.sha1 = row["sha1"]
        self.slug = row["slug"]
        self.asset = row["asset_id"]
        self.recordist = row["recordist"]
        self.latitude = float(row["latitude"]) if row["latitude"] else None
        self.longitude = float(row["longitude"]) if row["longitude"] else None
        self.path = PHOTOS / "macaulay-1200" / f"{self.asset}.jpg"

    @classmethod
    def load_all(cls):
        with open(PHOTOS / "manifest.csv", newline="") as handle:
            photos = [cls(row) for row in csv.DictReader(handle) if row["asset_id"]]
        return [p for p in photos if p.path.exists()]


class BoxCache:
    def __init__(self, path):
        self.path = path
        self.records = json.loads(path.read_text()) if path.exists() else {}

    def missing(self, photos):
        return [p for p in photos if p.asset not in self.records]

    def box(self, photo):
        return BirdBox.from_record(self.records[photo.asset])

    def put(self, photo, box):
        self.records[photo.asset] = box.to_record() if box else None

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.records))


class DetectorPool:
    """Several processes with a detector each; one detector does not get
    faster past eight threads."""

    _detector = None

    def __init__(self):
        self.pool = multiprocessing.get_context("spawn").Pool(DETECT_WORKERS, initializer=self._start)

    @classmethod
    def _start(cls):
        cls._detector = BirdDetector()

    @classmethod
    def _detect(cls, path):
        return cls._detector.box(open_photo(path))

    def boxes(self, photos):
        return zip(photos, self.pool.imap(self._detect, [p.path for p in photos]))

    def close(self):
        self.pool.close()


class FeatureCache:
    def __init__(self, path):
        self.path = path
        self.vectors = {}
        if path.exists():
            stored = np.load(path)
            self.vectors = dict(zip(stored["sha1"].tolist(), stored["vectors"]))

    def missing(self, photos):
        return [p for p in photos if p.sha1 not in self.vectors]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        keys = list(self.vectors)
        np.savez(self.path, sha1=np.array(keys), vectors=np.stack([self.vectors[k] for k in keys]))

    def matrix(self, photos):
        return np.stack([self.vectors[p.sha1] for p in photos])


class Validation:
    """Cross-validated accuracy, by pixels alone and with the location term.
    The atlas leaves out each photo's own recordist."""

    def __init__(self, photos, classes, vectors, atlas):
        self.photos = photos
        self.classes = classes
        self.labels = np.array([classes.index(p.slug) for p in photos])
        self.vectors = vectors
        self.atlas = atlas

    def metrics(self):
        folds = StratifiedKFold(n_splits=FOLDS, shuffle=True, random_state=0)
        image = np.log(cross_val_predict(new_classifier(), self.vectors, self.labels, cv=folds, method="predict_proba"))
        location = np.array([self._location(p) for p in self.photos])
        return {
            "photos_per_species": {c: int(np.sum(self.labels == i)) for i, c in enumerate(self.classes)},
            "image_only": self._recalls(image),
            "image_and_location": self._recalls(image + location),
        }

    def _location(self, photo):
        if photo.latitude is None:
            return np.zeros(len(self.classes))
        return self.atlas.log_likelihoods(self.classes, photo.latitude, photo.longitude, photo.recordist)

    def _recalls(self, scores):
        guesses = scores.argmax(axis=1)
        recalls = {c: float(np.mean(guesses[self.labels == i] == i)) for i, c in enumerate(self.classes)}
        return {"balanced_accuracy": float(np.mean(list(recalls.values()))), "per_species": recalls}


def new_classifier():
    return LogisticRegression(max_iter=3000, class_weight="balanced")


class Trainer:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self.photos = TrainingPhoto.load_all()
        self.classes = sorted({p.slug for p in self.photos})

    def run(self):
        if not self.photos:
            sys.exit("No 1200px photos under data/photos. Run `make photos` first.")
        run = Run("PHOTO ID TRAINING", ["detect", "embed", "validate", "fit"])
        boxes = BoxCache(BOXES)
        with run.stage("detect") as stage:
            self._detect(boxes, stage)
        features = FeatureCache(FEATURES)
        with run.stage("embed") as stage:
            self._embed(boxes, features, stage)
        vectors = features.matrix(self.photos)
        labels = np.array([self.classes.index(p.slug) for p in self.photos])
        atlas = Atlas.from_exports(PHOTOS / "macaulay-exports")
        with run.stage("validate") as stage:
            metrics = Validation(self.photos, self.classes, vectors, atlas).metrics()
            stage.update(1, 1)
        with run.stage("fit") as stage:
            self.model_dir.mkdir(parents=True, exist_ok=True)
            SpeciesHead(new_classifier().fit(vectors, labels), self.classes).save(self.model_dir / HEAD_FILE)
            atlas.save(self.model_dir / ATLAS_FILE)
            metrics.update(
                trained_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                embedder=BIOCLIP,
                features="whole frame + bird crop",
                location_radius_km=RADIUS_KM,
                validation=f"{FOLDS}-fold cross-validation",
                no_bird_found=sum(1 for p in self.photos if boxes.box(p) is None),
            )
            (self.model_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
            stage.update(1, 1)
        summary = (
            f"{len(self.photos)} photos, {len(self.classes)} species: "
            f"{metrics['image_only']['balanced_accuracy']:.1%} by pixels, "
            f"{metrics['image_and_location']['balanced_accuracy']:.1%} with location. "
            f"Model in {self.model_dir}"
        )
        run.note(summary)
        print(summary)

    def _detect(self, boxes, stage):
        todo = boxes.missing(self.photos)
        if todo:
            detectors = DetectorPool()
            for count, (photo, box) in enumerate(detectors.boxes(todo), 1):
                boxes.put(photo, box)
                stage.update(count, len(todo), extra=photo.slug)
                if count % 50 == 0:
                    boxes.save()
            detectors.close()
            boxes.save()
        stage.update(len(todo), len(todo))

    def _embed(self, boxes, features, stage):
        todo = features.missing(self.photos)
        if todo:
            import torch

            extractor = PhotoFeatures(None, BioclipEmbedder())
            torch.set_num_threads(EMBED_THREADS)
            for start in range(0, len(todo), BATCH):
                chunk = todo[start:start + BATCH]
                vectors = extractor.vectors([(open_photo(p.path), boxes.box(p)) for p in chunk])
                features.vectors.update(zip((p.sha1 for p in chunk), vectors))
                stage.update(start + len(chunk), len(todo))
                if (start // BATCH) % 10 == 0:
                    features.save()
            features.save()
        stage.update(len(todo), len(todo))


if __name__ == "__main__":
    Trainer(default_model_dir()).run()
