"""Cheap-wins experiment: can we lift alarm/song AUC with only existing data?

Three levers, no new downloads:
  1. Multi-label recovery — a clip tagged "alarm call, call" is a positive for
     BOTH classes, not garbage. The old pipeline dropped every comma'd label,
     throwing away >half the alarm data.
  2. Pooling — mean vs mean+std+max of the 3s BirdNET segments. std/max encode
     temporal spread ("this call repeats"), the actual alarm signature.
  3. Binary alarm-vs-rest sanity model — is the alarm signal there at all once
     we stop starving the class?

Reports per-class one-vs-rest AUC for each config vs. the current baseline
{alarm 0.68, call 0.72, flight 0.87, song 0.59}. Runs in .venv-birdnet:
  ../representation/.venv-birdnet/bin/python recover_and_pool.py
"""

import contextlib
import json
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

import pooling

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "data" / "corvid.db"
OUT = Path(__file__).resolve().parent / "results"
OUT.mkdir(exist_ok=True)
CACHE = OUT / "pooled_embeddings.npz"
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
DEVNULL = open(os.devnull, "w")


def _core_classes():
    """The one CORE list, from corpus.py — a script, and pure stdlib for this."""
    import importlib.util
    path = REPO / "pipelines" / "ingest" / "corpus.py"
    spec = importlib.util.spec_from_file_location("crowtools_corpus", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.CORE_CLASSES)


# Was a fourth hand-written copy of the class list. The copies had already
# drifted — crowgpt's is four, this and the server's are five — so the list
# lives in one importable place now and this reads it.
CORE = _core_classes()
CALL_TOKENS = {
    "call", "caw", "various calls", "various", "interaction calls",
    "interaction", "contact call", "short call", "elongated call",
    "nasal", "duet", "coo", "gurgle", "rattle",
}


def canon_token(tok: str):
    """Map one raw tag token to a core class, or None if not core."""
    t = tok.strip().lower()
    if not t:
        return None
    if any(k in t for k in ("alarm", "warning", "threat", "mobbing")):
        return "alarm call"
    if "flight" in t:
        return "flight call"
    if "song" in t:  # includes subsong / whisper song (rare)
        return "song"
    if "begging" in t:  # juvenile, and distinctive enough not to be a generic call
        return "begging"
    if t in CALL_TOKENS or t == "call":
        return "call"
    return None


def label_set(call_type: str):
    labels = set()
    for tok in (call_type or "").split(","):
        c = canon_token(tok)
        if c:
            labels.add(c)
    return labels


def load_rows():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT call_type, file_path FROM recordings "
        "WHERE downloaded = 1 AND file_path IS NOT NULL"
    ).fetchall()
    con.close()
    out = []
    for r in rows:
        labels = label_set(r["call_type"])
        if not labels:
            continue
        p = Path(r["file_path"])
        if p.exists():
            out.append((labels, p))
    return out


def pooled_embed(rec_segs):
    """mean + std + max over the clip's 3s segments -> 3072-dim."""
    M = np.array([s["embeddings"] for s in rec_segs])
    return np.concatenate([M.mean(0), M.std(0), M.max(0)])


def build_features():
    if CACHE.exists():
        d = np.load(CACHE, allow_pickle=True)
        return d["X"], [set(l) for l in d["Y"]]
    rows = load_rows()
    from crowgpt.progress import Run
    run = Run("recover_and_pool", ["embed"])
    print(f"recover_and_pool: embedding {len(rows)} clips (multi-label)…",
          file=sys.stderr, flush=True)
    with contextlib.redirect_stdout(DEVNULL):
        analyzer = Analyzer()
    X, Y = [], []
    with run.stage("embed") as stage:
        stage.say(f"{len(rows)} clips, multi-label")
        for i, (labels, p) in enumerate(rows):
            try:
                with contextlib.redirect_stdout(DEVNULL):
                    rec = Recording(analyzer, str(p), min_conf=0.1)
                    rec.extract_embeddings()
                if not rec.embeddings:
                    continue
                vec = pooled_embed(rec.embeddings)
                if np.isfinite(vec).all():
                    X.append(vec)
                    Y.append(labels)
            except Exception as ex:  # noqa: BLE001
                print(f"  fail {p.name}: {ex}", file=sys.stderr)
            if (i + 1) % 20 == 0:
                stage.update(i + 1, len(rows))
    X = np.array(X)
    np.savez(CACHE, X=X, Y=np.array([list(s) for s in Y], dtype=object))
    return X, Y


def per_class_auc(X, Y, classes):
    """One-vs-rest AUC per class on a (possibly multi-label) target."""
    out = {}
    for c in classes:
        yb = np.array([1 if c in s else 0 for s in Y])
        pos = int(yb.sum())
        if pos < 8 or pos == len(yb):
            out[c] = None
            continue
        n_splits = min(5, pos, len(yb) - pos)
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
        clf = make_pipeline(
            StandardScaler(),
            LogisticRegression(max_iter=5000, class_weight="balanced"),
        )
        proba = cross_val_predict(clf, X, yb, cv=cv, method="predict_proba")[:, 1]
        out[c] = round(float(roc_auc_score(yb, proba)), 3)
    return out, {c: int(sum(1 for s in Y if c in s)) for c in classes}


def main():
    X, Y = build_features()
    dim = X.shape[1] // pooling.BLOCKS  # blocks: mean, std, max
    mean_only = X[:, :dim]
    print("recover_and_pool: evaluating configs…", file=sys.stderr, flush=True)

    # The historical single-label numbers. No begging entry: it was dropped
    # rather than measured back then, so it has nothing to be compared against.
    baseline = {"alarm call": 0.681, "call": 0.716, "flight call": 0.87, "song": 0.592}

    auc_mean, counts = per_class_auc(mean_only, Y, CORE)
    auc_pool, _ = per_class_auc(X, Y, CORE)

    # Binary alarm-vs-rest sanity: is the signal there at all?
    y_alarm = np.array([1 if "alarm call" in s else 0 for s in Y])
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
    clf = make_pipeline(StandardScaler(),
                        LogisticRegression(max_iter=5000, class_weight="balanced"))
    proba = cross_val_predict(clf, X, y_alarm, cv=cv, method="predict_proba")[:, 1]
    alarm_auc = round(float(roc_auc_score(y_alarm, proba)), 3)
    alarm_f1 = round(float(f1_score(y_alarm, (proba >= 0.5).astype(int))), 3)

    report = {
        "n_clips": int(len(X)),
        "recovered_counts": counts,
        "old_single_label_counts": {"alarm call": 10, "call": 71, "flight call": 25, "song": 11},
        "per_class_auc": {
            "baseline_mean_singlelabel": baseline,
            "multilabel_mean": auc_mean,
            "multilabel_mean_std_max": auc_pool,
        },
        "binary_alarm_vs_rest": {"auc": alarm_auc, "f1": alarm_f1,
                                 "positives": int(y_alarm.sum())},
    }
    (OUT / "recover_and_pool.json").write_text(json.dumps(report, indent=2))

    def fmt(d):
        return "  ".join(f"{c.split()[0]:>7}={d.get(c) if d.get(c) is not None else '  – '}"
                         for c in CORE)

    print(f"\n=== cheap-wins experiment — {len(X)} clips ===")
    print("recovered counts:", counts, "(was", report["old_single_label_counts"], ")")
    print("\nper-class one-vs-rest AUC:")
    print(f"  baseline (mean, single-label)   {fmt(baseline)}")
    print(f"  multi-label   (mean)            {fmt(auc_mean)}")
    print(f"  multi-label   (mean+std+max)    {fmt(auc_pool)}")
    print(f"\nbinary alarm-vs-rest:  AUC={alarm_auc}  F1={alarm_f1}  "
          f"(n_alarm={int(y_alarm.sum())})")
    print(f"recover_and_pool: DONE  alarm {baseline['alarm call']}"
          f" -> {auc_pool['alarm call']}  song {baseline['song']}"
          f" -> {auc_pool['song']}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
