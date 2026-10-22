"""0082: fit the ear's history, then predict the sitting in progress.

Read-only against field.db. voice-0078's answers are never selected — the
prediction for it comes from clips + trials only, sealed before Ben's
remaining doses.
"""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "experiments"))

import numpy as np
import soundfile as sf

from crowgpt.embed import AstEmbedder
from crowgpt.progress import Run
from crowgpt.segment import Segmenter
from lib.dustprobe import clip_features

OUT = Path(__file__).resolve().parent
DB = REPO / "fieldserver" / "instance" / "field.db"
POOLS_DIR = HERE / "results" / "listening-pools"
TRAIN_POOLS = ("churn-spread-0053", "scrape-v3-0064", "longctx-0067",
               "longctx-0067b", "dust-0069")
PREDICT_POOL = "voice-0078"
SAMPLE_RATE = 24_000


def rows(query, args=()):
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(query, args)]
    finally:
        conn.close()


def graded_trials(pool):
    return rows("""
        SELECT t.id, t.kind, t.first_clip, t.second_clip, t.first_arm,
               t.second_arm, a.grade
        FROM listening_trials t
        JOIN listening_pools p ON p.id = t.pool_id
        JOIN listening_answers a ON a.trial_id = t.id
        WHERE p.name = ?""", (pool,))


def bare_trials(pool):
    return rows("""
        SELECT t.id, t.kind, t.first_clip, t.second_clip, t.first_arm,
               t.second_arm
        FROM listening_trials t
        JOIN listening_pools p ON p.id = t.pool_id
        WHERE p.name = ?""", (pool,))


def spearman(a, b):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    if ra.std() == 0 or rb.std() == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    run = Run("0082 — THE EAR'S HISTORY", ["embed", "fit", "predict"])
    seg = Segmenter()
    embedder = AstEmbedder(device="cpu")
    cache = {}

    def features_of(pool, clip):
        key = (pool, clip)
        if key not in cache:
            # Older pools were written at other rates (churn-spread is not
            # 24 kHz); every consumer here takes the file's own rate.
            audio, sr = sf.read(POOLS_DIR / pool / clip, dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            emb = embedder.embed([audio], sr)[0]
            f = clip_features(seg, audio, sr) or {}
            cache[key] = np.concatenate(
                [emb, [f.get("pitch_strength", 0.0), f.get("flatness", 0.0),
                       len(audio) / sr]])
        return cache[key]

    with run.stage("embed") as stage:
        data = {}
        needed = []
        for pool in TRAIN_POOLS:
            data[pool] = graded_trials(pool)
            for t in data[pool]:
                needed.extend([(pool, t["first_clip"]),
                               (pool, t["second_clip"])])
        predict_trials = bare_trials(PREDICT_POOL)
        for t in predict_trials:
            needed.extend([(PREDICT_POOL, t["first_clip"]),
                           (PREDICT_POOL, t["second_clip"])])
        needed = list(dict.fromkeys(needed))
        for n, key in enumerate(needed):
            features_of(*key)
            stage.update(n + 1, len(needed), extra=key[1][:32])

    with run.stage("fit") as stage:
        from sklearn.linear_model import Ridge

        def xy(pools):
            x, y, kinds = [], [], []
            for pool in pools:
                for t in data[pool]:
                    delta = features_of(pool, t["first_clip"]) \
                        - features_of(pool, t["second_clip"])
                    x.append(delta)
                    y.append(t["grade"])
                    kinds.append((t["kind"], t["first_arm"], t["second_arm"]))
            return np.stack(x), np.asarray(y, dtype=float), kinds

        report = {"answers": {p: len(data[p]) for p in TRAIN_POOLS}}
        held_out = {}
        for pool in TRAIN_POOLS:
            train = [p for p in TRAIN_POOLS if p != pool]
            x_tr, y_tr, _ = xy(train)
            x_te, y_te, kinds = xy([pool])
            model = Ridge(alpha=100.0).fit(x_tr, y_tr)
            pred = model.predict(x_te)
            fold = {"n": len(y_te), "spearman": round(spearman(pred, y_te), 3)}
            catches = [(p, y, k) for p, y, k in zip(pred, y_te, kinds)
                       if k[0] == "catch"]
            if catches:
                right = sum(
                    1 for p, y, k in catches
                    if (p > 0) == (k[1] == "real") and abs(y) > 0)
                graded = sum(1 for _, y, _ in catches if abs(y) > 0)
                fold["catch_direction_acc"] = round(right / graded, 3) \
                    if graded else None
            held_out[pool] = fold
            stage.update(list(TRAIN_POOLS).index(pool) + 1, len(TRAIN_POOLS),
                         extra=pool)
        report["held_out"] = held_out
        report["mean_spearman"] = round(float(np.mean(
            [f["spearman"] for f in held_out.values()])), 3)
        run.note(f"held-out: {held_out}")

    with run.stage("predict") as stage:
        x_all, y_all, _ = xy(TRAIN_POOLS)
        model = Ridge(alpha=100.0).fit(x_all, y_all)
        toward = defaultdict(list)
        for t in predict_trials:
            if t["kind"] != "compare":
                continue
            delta = features_of(PREDICT_POOL, t["first_clip"]) \
                - features_of(PREDICT_POOL, t["second_clip"])
            pred = float(model.predict(delta[None])[0])
            toward[t["first_arm"]].append(pred)
        # A positive grade means "toward the first clip"; fold both orders
        # into one number per arm pairing.
        margins = [p if arm == "calltype" else -p
                   for arm, preds in toward.items() for p in preds]
        report["sealed_voice_0078_prediction"] = {
            "mean_margin_toward_calltype": round(float(np.mean(margins)), 3),
            "share_favoring_calltype": round(
                float(np.mean([m > 0 for m in margins])), 3),
            "n_compare_trials": len(margins),
            "reading": "positive favors model-calltype, negative favors b32",
        }
        stage.update(1, 1)
        run.note(f"sealed: {report['sealed_voice_0078_prediction']}")

    (OUT / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
