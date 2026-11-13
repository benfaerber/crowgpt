"""Can BioCLIP 2, zero-shot, name the corvid in a photo?

Reads the thumbnails `tools/import_ml_photos.py` put in data/photos, embeds
each once with BioCLIP 2 (cached by sha1, so adding a species embeds only the
new photos), and scores top-1 against three candidate lists of increasing
difficulty, then trains a logistic-regression head on the same embeddings
and scores it by 5-fold cross-validation for comparison. CPU only.

    uv run --with open_clip_torch --with torch --with numpy --with scikit-learn \\
        python experiments/0090-can-bioclip-name-the-crow-in-a-photo/run.py
"""

import csv
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import open_clip
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
PHOTOS = DATA / "photos"
MODEL = "hf-hub:imageomics/bioclip-2"
CACHE = PHOTOS / "embeddings" / "bioclip-2.npz"
BATCH = 32

SPECIES = {
    "american-crow": ("Corvus brachyrhynchos", "American Crow"),
    "common-raven": ("Corvus corax", "Common Raven"),
    "black-billed-magpie": ("Pica hudsonia", "Black-billed Magpie"),
    "fish-crow": ("Corvus ossifragus", "Fish Crow"),
    "chihuahuan-raven": ("Corvus cryptoleucus", "Chihuahuan Raven"),
    "carrion-crow": ("Corvus corone", "Carrion Crow"),
    "hooded-crow": ("Corvus cornix", "Hooded Crow"),
    "rook": ("Corvus frugilegus", "Rook"),
    "eurasian-jackdaw": ("Coloeus monedula", "Eurasian Jackdaw"),
    "large-billed-crow": ("Corvus macrorhynchos", "Large-billed Crow"),
    "house-crow": ("Corvus splendens", "House Crow"),
}

CANDIDATE_SETS = {
    "utah": ["american-crow", "common-raven", "black-billed-magpie"],
    "north-america": ["american-crow", "common-raven", "black-billed-magpie", "fish-crow", "chihuahuan-raven"],
    "all": list(SPECIES),
}

TEMPLATES = ("a photo of {sci}.", "a photo of {common}.", "a photo of {common}, {sci}.")


class Photo:
    def __init__(self, row):
        self.sha1 = row["sha1"]
        self.slug = row["slug"]
        self.path = PHOTOS / row["path"]


class Embedder:
    def __init__(self):
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(MODEL)
        self.tokenizer = open_clip.get_tokenizer(MODEL)
        self.model.eval()
        torch.set_num_threads(os.cpu_count())

    @torch.no_grad()
    def images(self, paths):
        batch = torch.stack([self.preprocess(Image.open(p).convert("RGB")) for p in paths])
        vectors = self.model.encode_image(batch)
        return (vectors / vectors.norm(dim=-1, keepdim=True)).numpy()

    @torch.no_grad()
    def species(self, slug):
        sci, common = SPECIES[slug]
        tokens = self.tokenizer([t.format(sci=sci, common=common) for t in TEMPLATES])
        vectors = self.model.encode_text(tokens)
        vectors = vectors / vectors.norm(dim=-1, keepdim=True)
        mean = vectors.mean(dim=0)
        return (mean / mean.norm()).numpy()


class EmbeddingCache:
    def __init__(self, path):
        self.path = path
        self.vectors = {}
        if path.exists():
            stored = np.load(path)
            self.vectors = dict(zip(stored["sha1"], stored["vectors"]))

    def missing(self, photos):
        return [p for p in photos if p.sha1 not in self.vectors]

    def add(self, photos, vectors):
        self.vectors.update(zip((p.sha1 for p in photos), vectors))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        keys = list(self.vectors)
        np.savez(self.path, sha1=np.array(keys), vectors=np.stack([self.vectors[k] for k in keys]))

    def matrix(self, photos):
        return np.stack([self.vectors[p.sha1] for p in photos])


class Scorer:
    def __init__(self, photos, image_vectors, text_vectors):
        self.photos = photos
        self.images = image_vectors
        self.text = text_vectors

    def zero_shot(self, name, candidates):
        text = np.stack([self.text[c] for c in candidates])
        guesses = (self.images @ text.T).argmax(axis=1)
        return self._report(f"## zero-shot, {name}: {len(candidates)} candidates", candidates, guesses)

    def trained(self, name, candidates):
        present = [c for c in candidates if any(p.slug == c for p in self.photos)]
        rows = [i for i, p in enumerate(self.photos) if p.slug in present]
        labels = np.array([present.index(self.photos[i].slug) for i in rows])
        head = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced")
        folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
        predicted = cross_val_predict(head, self.images[rows], labels, cv=folds)
        guesses = np.full(len(self.photos), -1)
        guesses[rows] = predicted
        return self._report(f"## trained head (5-fold CV), {name}: {len(present)} classes with photos",
                            present, guesses)

    def learning_curve(self, name, candidates, sizes=(50, 100, 200, 320)):
        present = [c for c in candidates if any(p.slug == c for p in self.photos)]
        rows = np.array([i for i, p in enumerate(self.photos) if p.slug in present])
        labels = np.array([present.index(self.photos[i].slug) for i in rows])
        folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
        rng = np.random.default_rng(0)
        lines = [f"## learning curve, {name}: balanced accuracy by training photos per species"]
        for size in sizes:
            scores = []
            for train, test in folds.split(rows, labels):
                picked = np.concatenate([rng.permutation(train[labels[train] == k])[:size] for k in range(len(present))])
                head = LogisticRegression(max_iter=2000, class_weight="balanced")
                head.fit(self.images[rows[picked]], labels[picked])
                guessed = head.predict(self.images[rows[test]])
                scores.append(np.mean([np.mean(guessed[labels[test] == k] == k) for k in range(len(present))]))
            lines.append(f"  {size:4d} per species  {np.mean(scores):6.1%}")
        return "\n".join(lines)

    def _report(self, title, candidates, guesses):
        lines = [title]
        for slug in sorted({p.slug for p in self.photos}):
            rows = [i for i, p in enumerate(self.photos) if p.slug == slug]
            if slug not in candidates:
                lines.append(f"  {slug}: not a candidate in this set, skipped")
                continue
            counts = Counter(candidates[g] for g in guesses[rows])
            accuracy = counts[slug] / len(rows)
            confusions = ", ".join(f"{s} {n}" for s, n in counts.most_common() if s != slug)
            lines.append(f"  {slug:22s} n={len(rows):5d}  top-1 {accuracy:6.1%}  wrong: {confusions or '-'}")
        return "\n".join(lines)


def load_photos():
    with open(PHOTOS / "manifest.csv", newline="") as handle:
        return [Photo(row) for row in csv.DictReader(handle) if row["slug"] in SPECIES]


def main():
    photos = load_photos()
    run = Run("0090 — BIOCLIP PHOTO ID", ["embed", "score"])
    cache = EmbeddingCache(CACHE)
    embedder = Embedder()
    with run.stage("embed") as stage:
        todo = cache.missing(photos)
        for start in range(0, len(todo), BATCH):
            chunk = todo[start:start + BATCH]
            cache.add(chunk, embedder.images([p.path for p in chunk]))
            stage.update(start + len(chunk), len(todo))
            if (start // BATCH) % 10 == 0:
                cache.save()
        cache.save()
        stage.update(len(todo), len(todo))
    with run.stage("score") as stage:
        scorer = Scorer(photos, cache.matrix(photos), {s: embedder.species(s) for s in SPECIES})
        report = "\n\n".join(
            [scorer.zero_shot(n, c) for n, c in CANDIDATE_SETS.items()]
            + [scorer.trained(n, c) for n, c in CANDIDATE_SETS.items()]
            + [scorer.learning_curve(n, c) for n, c in CANDIDATE_SETS.items()]
        )
        print(report)
        run.note(report)
        stage.update(1, 1)


if __name__ == "__main__":
    main()
