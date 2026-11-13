"""Does cropping to the bird before embedding help tell crows from ravens?

0090 embeds the whole frame at 224px, so a bird that fills a tenth of the
photo keeps a bill a few pixels long. This fetches the 1200px version of each
photo of the four North American black corvids, finds the bird with an
off-the-shelf COCO detector (torchvision Faster R-CNN), crops a square around
it, and embeds the crop with BioCLIP 2. The same cross-validated logistic head
is then scored on whole-frame embeddings (0090's cache), crop embeddings, and
both concatenated, on identical folds. Run 0090 first.

Everything is cached under data/photos (large photos by asset id, boxes,
crop embeddings), so a re-run only scores. CPU only.

    uv run --with open_clip_torch --with torch --with torchvision --with numpy --with scikit-learn \\
        python experiments/0092-does-cropping-to-the-bird-help-photo-id/run.py
"""

import csv
import json
import multiprocessing
import os
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np
import open_clip
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from torchvision.models.detection import FasterRCNN_ResNet50_FPN_V2_Weights, fasterrcnn_resnet50_fpn_v2
from torchvision.transforms.functional import to_tensor

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
PHOTOS = DATA / "photos"
LARGE = PHOTOS / "macaulay-1200"
BOXES = PHOTOS / "boxes" / "fasterrcnn-resnet50-fpn-v2.json"
WHOLE_CACHE = PHOTOS / "embeddings" / "bioclip-2.npz"
CROP_CACHE = PHOTOS / "embeddings" / "bioclip-2-crop.npz"
ASSET_URL = "https://cdn.download.ams.birds.cornell.edu/api/v2/asset/{asset}/1200"
USER_AGENT = "crowgpt-photo-import/1.0"
PAUSE_SECONDS = 0.5
MODEL = "hf-hub:imageomics/bioclip-2"
SPECIES = ["american-crow", "common-raven", "fish-crow", "chihuahuan-raven"]
PAIRS = {"crow vs raven": ["american-crow", "common-raven"], "four black corvids": SPECIES}
CONFIDENT = 0.5
FAINT = 0.3
MARGIN = 1.2
BATCH = 32
DETECT_WORKERS = 4
DETECT_THREADS = 8


class Photo:
    def __init__(self, row):
        self.sha1 = row["sha1"]
        self.slug = row["slug"]
        self.asset = row["asset_id"]
        self.large_path = LARGE / f"{self.asset}.jpg"

    def fetch_large(self):
        if self.large_path.exists():
            return
        time.sleep(PAUSE_SECONDS)
        request = urllib.request.Request(ASSET_URL.format(asset=self.asset), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            content = response.read()
        self.large_path.parent.mkdir(parents=True, exist_ok=True)
        self.large_path.write_bytes(content)

    def image(self):
        return Image.open(self.large_path).convert("RGB")


class BirdDetector:
    def __init__(self):
        weights = FasterRCNN_ResNet50_FPN_V2_Weights.DEFAULT
        self.model = fasterrcnn_resnet50_fpn_v2(weights=weights, box_score_thresh=FAINT).eval()
        self.bird = weights.meta["categories"].index("bird")

    @torch.no_grad()
    def box(self, image):
        """The largest confidently detected bird, else the best faint one,
        else None. The subject of a bird photo is usually its biggest bird."""
        found = self.model([to_tensor(image)])[0]
        birds = [(b.tolist(), s.item()) for b, l, s in zip(found["boxes"], found["labels"], found["scores"])
                 if l.item() == self.bird]
        if not birds:
            return None
        confident = [b for b in birds if b[1] >= CONFIDENT]
        if confident:
            box, score = max(confident, key=lambda b: (b[0][2] - b[0][0]) * (b[0][3] - b[0][1]))
        else:
            box, score = max(birds, key=lambda b: b[1])
        return {"box": box, "score": score, "birds": len(birds)}


class DetectorPool:
    """Faster R-CNN on CPU is fastest at about eight threads a process, so
    the photos go through several processes with a detector each."""

    _detector = None

    def __init__(self):
        self.pool = multiprocessing.get_context("spawn").Pool(DETECT_WORKERS, initializer=self._start)

    @classmethod
    def _start(cls):
        torch.set_num_threads(DETECT_THREADS)
        cls._detector = BirdDetector()

    @classmethod
    def _detect(cls, path):
        return cls._detector.box(Image.open(path).convert("RGB"))

    def boxes(self, photos):
        return zip(photos, self.pool.imap(self._detect, [p.large_path for p in photos]))

    def close(self):
        self.pool.close()


class BoxStore:
    def __init__(self, path):
        self.path = path
        self.boxes = json.loads(path.read_text()) if path.exists() else {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.boxes))

    def crop(self, photo):
        """A square around the bird with a margin, kept inside the frame.
        The whole frame when no bird was found."""
        image = photo.image()
        found = self.boxes[photo.asset]
        if found is None:
            return image
        left, top, right, bottom = found["box"]
        side = min(max(right - left, bottom - top) * MARGIN, image.width, image.height)
        x = min(max((left + right) / 2 - side / 2, 0), image.width - side)
        y = min(max((top + bottom) / 2 - side / 2, 0), image.height - side)
        return image.crop((int(x), int(y), int(x + side), int(y + side)))

    def frame_share(self, photo):
        found = self.boxes[photo.asset]
        if found is None:
            return None
        left, top, right, bottom = found["box"]
        with Image.open(photo.large_path) as image:
            return (right - left) * (bottom - top) / (image.width * image.height)


class EmbeddingCache:
    def __init__(self, path):
        self.path = path
        self.vectors = {}
        if path.exists():
            stored = np.load(path)
            self.vectors = dict(zip(stored["sha1"], stored["vectors"]))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        keys = list(self.vectors)
        np.savez(self.path, sha1=np.array(keys), vectors=np.stack([self.vectors[k] for k in keys]))

    def matrix(self, photos):
        return np.stack([self.vectors[p.sha1] for p in photos])


class Embedder:
    def __init__(self):
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(MODEL)
        self.model.eval()

    @torch.no_grad()
    def embed(self, images):
        vectors = self.model.encode_image(torch.stack([self.preprocess(i) for i in images]))
        return (vectors / vectors.norm(dim=-1, keepdim=True)).numpy()


class Comparison:
    def __init__(self, photos, features, shares):
        self.photos = photos
        self.features = features
        self.shares = shares

    def report(self, title, classes):
        rows = [i for i, p in enumerate(self.photos) if p.slug in classes]
        labels = np.array([classes.index(self.photos[i].slug) for i in rows])
        folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
        guesses = {}
        for name, matrix in self.features.items():
            head = LogisticRegression(max_iter=3000, class_weight="balanced")
            guesses[name] = cross_val_predict(head, matrix[rows], labels, cv=folds)
        lines = [f"## {title}: top-1 by what the head sees", "  " + " " * 24 + "".join(f"{n:>14s}" for n in guesses)]
        for index, slug in enumerate(classes):
            mine = labels == index
            lines.append(f"  {slug:18s} n={mine.sum():3d}" + "".join(f"{np.mean(g[mine] == index):14.1%}" for g in guesses.values()))
        lines.append(f"  {'balanced':24s}" + "".join(
            f"{np.mean([np.mean(g[labels == k] == k) for k in range(len(classes))]):14.1%}" for g in guesses.values()))
        whole, crop = guesses["whole"] == labels, guesses["crop"] == labels
        lines.append(f"  crop fixes {np.sum(~whole & crop)} photos the whole frame got wrong and breaks {np.sum(whole & ~crop)}")
        both = guesses["whole+crop"] == labels
        lines.append(f"  whole+crop fixes {np.sum(~whole & both)} and breaks {np.sum(whole & ~both)}")
        lines.append("  by how much of the frame the bird fills:")
        for band, members in self._bands(rows).items():
            if members.any():
                lines.append(f"    {band:22s} n={members.sum():4d}" + "".join(
                    f"{np.mean(g[members] == labels[members]):14.1%}" for g in guesses.values()))
        return "\n".join(lines)

    def _bands(self, rows):
        shares = np.array([np.nan if self.shares[i] is None else self.shares[i] for i in rows])
        found = ~np.isnan(shares)
        low, high = np.quantile(shares[found], [1 / 3, 2 / 3])
        return {
            "no bird found": ~found,
            f"small (<{low:.0%})": found & (shares < low),
            f"medium ({low:.0%}-{high:.0%})": found & (shares >= low) & (shares < high),
            f"large (>{high:.0%})": found & (shares >= high),
        }


def load_photos():
    with open(PHOTOS / "manifest.csv", newline="") as handle:
        return [Photo(row) for row in csv.DictReader(handle) if row["slug"] in SPECIES and row["asset_id"]]


def main():
    torch.set_num_threads(16)
    photos = load_photos()
    run = Run("0092 — CROP TO THE BIRD", ["fetch 1200px", "detect", "embed crops", "score"])
    with run.stage("fetch 1200px") as stage:
        for count, photo in enumerate(photos, 1):
            photo.fetch_large()
            stage.update(count, len(photos), extra=photo.slug)
    boxes = BoxStore(BOXES)
    with run.stage("detect") as stage:
        todo = [p for p in photos if p.asset not in boxes.boxes]
        if todo:
            detectors = DetectorPool()
            for count, (photo, box) in enumerate(detectors.boxes(todo), 1):
                boxes.boxes[photo.asset] = box
                stage.update(count, len(todo), extra=photo.slug)
                if count % 50 == 0:
                    boxes.save()
            detectors.close()
        boxes.save()
        stage.update(len(todo), len(todo))
    crops = EmbeddingCache(CROP_CACHE)
    with run.stage("embed crops") as stage:
        todo = [p for p in photos if p.sha1 not in crops.vectors]
        embedder = Embedder() if todo else None
        for start in range(0, len(todo), BATCH):
            chunk = todo[start:start + BATCH]
            crops.vectors.update(zip((p.sha1 for p in chunk), embedder.embed([boxes.crop(p) for p in chunk])))
            stage.update(start + len(chunk), len(todo))
            crops.save()
        stage.update(len(todo), len(todo))
    with run.stage("score") as stage:
        whole = EmbeddingCache(WHOLE_CACHE).matrix(photos)
        crop = crops.matrix(photos)
        features = {"whole": whole, "crop": crop, "whole+crop": np.hstack([whole, crop])}
        comparison = Comparison(photos, features, [boxes.frame_share(p) for p in photos])
        missed = Counter(p.slug for p in photos if boxes.boxes[p.asset] is None)
        report = "\n\n".join(
            [f"no bird found in {sum(missed.values())} of {len(photos)} photos: {dict(missed)}"]
            + [comparison.report(title, classes) for title, classes in PAIRS.items()]
        )
        print(report)
        run.note(report)
        stage.update(1, 1)


if __name__ == "__main__":
    main()
