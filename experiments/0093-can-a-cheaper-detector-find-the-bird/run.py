"""Can a cheaper detector find the bird without costing the crop's gain?

0092's crop comes from Faster R-CNN ResNet-50 FPN v2, which is two thirds of
a photo's time once the models are loaded: 2.7 s on two laptop cores, far
more on the hosted box's two older ones. This scores the same whole+crop
head with the crop taken from cheaper detectors instead: the same network
at a 448px short side, and Faster R-CNN MobileNetV3-Large FPN. Same photos,
same folds, same BioCLIP 2 embedder as 0092. Run 0092 first; it leaves the
1200px photos, the reference boxes and the whole-frame embeddings.

    uv run --with open_clip_torch --with torch --with torchvision --with numpy --with scikit-learn \\
        python experiments/0093-can-a-cheaper-detector-find-the-bird/run.py
"""

import importlib.util
import sys
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from torchvision.models.detection import (
    FasterRCNN_MobileNet_V3_Large_FPN_Weights,
    FasterRCNN_ResNet50_FPN_V2_Weights,
    fasterrcnn_mobilenet_v3_large_fpn,
    fasterrcnn_resnet50_fpn_v2,
)
from torchvision.transforms.functional import to_tensor

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "crop_experiment", REPO / "experiments" / "0092-does-cropping-to-the-bird-help-photo-id" / "run.py")
crop_experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crop_experiment)
Run = crop_experiment.Run

PHOTOS = crop_experiment.PHOTOS
REFERENCE = "resnet50 800px"
TIMING_THREADS = 2
TIMING_PHOTOS = 12


class Variant:
    """One detector: where its boxes and crop embeddings are cached, and how
    to build it."""

    def __init__(self, name, slug, build):
        self.name = name
        self.build = build
        self.boxes = crop_experiment.BoxStore(PHOTOS / "boxes" / f"{slug}.json")
        self.crops = crop_experiment.EmbeddingCache(PHOTOS / "embeddings" / f"bioclip-2-crop-{slug}.npz")
        self.seconds = None


class Detector(crop_experiment.BirdDetector):
    def __init__(self, model, weights):
        self.model = model.eval()
        self.bird = weights.meta["categories"].index("bird")


def resnet50_small():
    weights = FasterRCNN_ResNet50_FPN_V2_Weights.DEFAULT
    return Detector(fasterrcnn_resnet50_fpn_v2(
        weights=weights, box_score_thresh=crop_experiment.FAINT, min_size=448, max_size=746), weights)


def mobilenet():
    weights = FasterRCNN_MobileNet_V3_Large_FPN_Weights.DEFAULT
    return Detector(fasterrcnn_mobilenet_v3_large_fpn(weights=weights, box_score_thresh=crop_experiment.FAINT), weights)


def reference():
    return crop_experiment.BirdDetector()


class Agreement:
    """How a variant's boxes compare with the reference detector's."""

    def __init__(self, photos, reference_boxes, boxes):
        self.pairs = [(reference_boxes.boxes[p.asset], boxes.boxes[p.asset]) for p in photos]

    @staticmethod
    def _iou(a, b):
        left, top = max(a[0], b[0]), max(a[1], b[1])
        right, bottom = min(a[2], b[2]), min(a[3], b[3])
        overlap = max(right - left, 0) * max(bottom - top, 0)
        area = lambda box: (box[2] - box[0]) * (box[3] - box[1])  # noqa: E731
        return overlap / (area(a) + area(b) - overlap)

    def line(self):
        both = [self._iou(r["box"], v["box"]) for r, v in self.pairs if r and v]
        lost = sum(1 for r, v in self.pairs if r and not v)
        gained = sum(1 for r, v in self.pairs if v and not r)
        return (f"same bird (IoU over 0.5) in {np.mean(np.array(both) > 0.5):.1%} of {len(both)} shared photos, "
                f"median IoU {np.median(both):.2f}; misses {lost} birds the reference found, finds {gained} it missed")


class Scoreboard:
    def __init__(self, photos, whole):
        self.photos = photos
        self.whole = whole

    def accuracy(self, classes, crop=None):
        rows = [i for i, p in enumerate(self.photos) if p.slug in classes]
        labels = np.array([classes.index(self.photos[i].slug) for i in rows])
        matrix = self.whole[rows] if crop is None else np.hstack([self.whole[rows], crop[rows]])
        head = LogisticRegression(max_iter=3000, class_weight="balanced")
        folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
        guesses = cross_val_predict(head, matrix, labels, cv=folds)
        return np.mean([np.mean(guesses[labels == k] == k) for k in range(len(classes))])


def seconds_per_photo(detector, photos):
    torch.set_num_threads(TIMING_THREADS)
    images = [p.image() for p in photos[:TIMING_PHOTOS]]
    detector.box(images[0])
    started = time.perf_counter()
    for image in images:
        detector.box(image)
    return (time.perf_counter() - started) / len(images)


def main():
    photos = crop_experiment.load_photos()
    variants = [
        Variant(REFERENCE, "fasterrcnn-resnet50-fpn-v2", reference),
        Variant("resnet50 448px", "fasterrcnn-resnet50-fpn-v2-448", resnet50_small),
        Variant("mobilenet-v3", "fasterrcnn-mobilenet-v3-large-fpn", mobilenet),
    ]
    variants[0].crops = crop_experiment.EmbeddingCache(crop_experiment.CROP_CACHE)
    total = len(photos) * len(variants)
    run = Run("0093 — A CHEAPER BIRD DETECTOR", ["detect", "embed crops", "score"])
    with run.stage("detect") as stage:
        for index, variant in enumerate(variants):
            detector = variant.build()
            variant.seconds = seconds_per_photo(detector, photos)
            torch.set_num_threads(16)
            for count, photo in enumerate(photos, 1):
                if photo.asset not in variant.boxes.boxes:
                    variant.boxes.boxes[photo.asset] = detector.box(photo.image())
                    if count % 50 == 0:
                        variant.boxes.save()
                        stage.update(index * len(photos) + count, total, extra=variant.name)
            variant.boxes.save()
            stage.update((index + 1) * len(photos), total, extra=variant.name)
    with run.stage("embed crops") as stage:
        embedder = None
        for index, variant in enumerate(variants):
            todo = [p for p in photos if p.sha1 not in variant.crops.vectors]
            for start in range(0, len(todo), crop_experiment.BATCH):
                embedder = embedder or crop_experiment.Embedder()
                chunk = todo[start:start + crop_experiment.BATCH]
                variant.crops.vectors.update(
                    zip((p.sha1 for p in chunk), embedder.embed([variant.boxes.crop(p) for p in chunk])))
                variant.crops.save()
                stage.update(index * len(photos) + len(photos) - len(todo) + start + len(chunk), total, extra=variant.name)
            stage.update((index + 1) * len(photos), total, extra=variant.name)
    with run.stage("score") as stage:
        board = Scoreboard(photos, crop_experiment.EmbeddingCache(crop_experiment.WHOLE_CACHE).matrix(photos))
        pairs = crop_experiment.PAIRS
        lines = [f"{len(photos)} photos; detector seconds a photo on {TIMING_THREADS} threads",
                 f"  {'crop from':18s}{'s/photo':>9s}{'no bird':>9s}" + "".join(f"{t:>22s}" for t in pairs),
                 f"  {'(whole frame only)':18s}{'':>9s}{'':>9s}"
                 + "".join(f"{board.accuracy(c):22.1%}" for c in pairs.values())]
        for variant in variants:
            missed = sum(1 for p in photos if variant.boxes.boxes[p.asset] is None)
            lines.append(f"  {variant.name:18s}{variant.seconds:9.2f}{missed:9d}" + "".join(
                f"{board.accuracy(c, variant.crops.matrix(photos)):22.1%}" for c in pairs.values()))
        for variant in variants[1:]:
            lines.append(f"  {variant.name}: " + Agreement(photos, variants[0].boxes, variant.boxes).line())
        report = "\n".join(lines)
        print(report)
        run.note(report)
        stage.update(1, 1)


if __name__ == "__main__":
    main()
