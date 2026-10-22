"""Train a per-species call-type head from a species manifest.

The manifest arrives with the corpus — the private corpus tooling writes it;
this reads what it left in data/species/<slug>/.

Whole-clip pooled BirdNET features (shared pooling.pool) + the archives' `type`
mapped to CORE classes (shared recover_and_pool.label_set). Trains a logreg head
and writes it where the demo auto-discovers it:
  pipelines/training/models/<slug>/calltype_clf.joblib  (+ metrics.json)

Weak `type` labels, so expect a rough head — the demo's reliability badges show
it. Runs in the BirdNET venv (birdnetlib + sklearn):
  ../representation/.venv-birdnet/bin/python train_species.py --slug carrion-crow --jobs 30
"""

import argparse
import contextlib
import json
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("DATA_DIR") or REPO / "data")
TRAINING = REPO / "pipelines" / "training"
MODELS = TRAINING / "models"
sys.path.insert(0, str(TRAINING))
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
import pooling  # noqa: E402
from pooling import pool  # noqa: E402
from recover_and_pool import CORE, label_set  # noqa: E402  — XC type -> CORE set

from crowgpt.progress import Run  # noqa: E402

MIN_PER_CLASS = 8
DEVNULL = open(os.devnull, "w")
_ANALYZER = None


def _worker_init():
    global _ANALYZER
    with contextlib.redirect_stdout(DEVNULL):
        _ANALYZER = Analyzer()


def _embed(item):
    path, type_str = item
    labels = label_set(type_str)
    if not labels:
        return None
    try:
        with contextlib.redirect_stdout(DEVNULL):
            rec = Recording(_ANALYZER, path, min_conf=0.1)
            rec.extract_embeddings()
    except Exception:  # noqa: BLE001
        return None
    if not rec.embeddings:
        return None
    vec = pool([s["embeddings"] for s in rec.embeddings])
    if not np.isfinite(vec).all():
        return None
    return vec, sorted(labels)


def per_class_auc(X, Y):
    out = {}
    for c in CORE:
        yb = np.array([1 if c in s else 0 for s in Y])
        pos = int(yb.sum())
        if pos < MIN_PER_CLASS or pos == len(yb):
            out[c] = None
            continue
        n_splits = min(5, pos, len(yb) - pos)
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
        clf = make_pipeline(StandardScaler(),
                            LogisticRegression(max_iter=5000, class_weight="balanced"))
        proba = cross_val_predict(clf, X, yb, cv=cv, method="predict_proba")[:, 1]
        out[c] = round(float(roc_auc_score(yb, proba)), 3)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--slug", required=True)
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    args = parser.parse_args()

    manifest_path = DATA / "species" / args.slug / "manifest.json"
    if not manifest_path.exists():
        sys.exit(
            f"No manifest at {manifest_path}. The corpus must supply this species\n"
            f"first — fetch it with the private corpus tooling, with DATA_DIR\n"
            f"pointed here."
        )
    recs = json.loads(manifest_path.read_text())["recordings"]
    items = [(r["path"], r["type"]) for r in recs if Path(r["path"]).exists()]
    run = Run(f"train {args.slug}", ["embed"])
    print(f"train {args.slug}: embedding {len(items)} clips — {args.jobs} worker(s)",
          flush=True)

    X, Y = [], []
    if args.jobs <= 1:
        _worker_init()
        results = map(_embed, items)
    else:
        ex = ProcessPoolExecutor(max_workers=args.jobs, initializer=_worker_init)
        results = ex.map(_embed, items, chunksize=4)
    done = 0
    with run.stage("embed") as stage:
        stage.say(f"{len(items)} clips — {args.jobs} worker(s)")
        for r in results:
            done += 1
            if r is not None:
                X.append(r[0])
                Y.append(r[1])
            if done % 100 == 0:
                stage.update(done, len(items))
    X = np.array(X)
    if len(X) < MIN_PER_CLASS * 2:
        sys.exit(f"Only {len(X)} labelled clips — too few to train a head.")

    auc = per_class_auc(X, Y)

    # Final shippable model: multiclass logreg on the clean single-label subset.
    single = [(x, next(iter(s))) for x, s in zip(X, Y) if len(s) == 1]
    Xs = np.array([x for x, _ in single])
    ys = np.array([c for _, c in single])
    strong = {c for c in set(ys) if (ys == c).sum() >= MIN_PER_CLASS}
    keep = np.array([c in strong for c in ys])
    Xs, ys = Xs[keep], ys[keep]
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=5000, class_weight="balanced")).fit(Xs, ys)

    out_dir = MODELS / args.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    # `feature` and `dim` are what analyzer/birdnet.py checks at load, so a head
    # trained on one backbone cannot be silently served by another.
    joblib.dump({"model": model, "classes": list(model.classes_),
                 "feature": pooling.FEATURE, "backbone": pooling.BACKBONE,
                 "dim": int(X.shape[1])},
                out_dir / "calltype_clf.joblib")
    (out_dir / "metrics.json").write_text(json.dumps({
        "n": int(len(X)), "n_single_label": int(len(ys)),
        "classes": dict(Counter(ys)), "per_class_auc": auc,
    }, indent=2))

    run.note(f"done -> {out_dir}/calltype_clf.joblib  "
             f"classes={list(model.classes_)}  AUC={auc}")
    print(f"train {args.slug}: done -> {out_dir}/calltype_clf.joblib  "
          f"classes={list(model.classes_)}  AUC={auc}", flush=True)


if __name__ == "__main__":
    main()
