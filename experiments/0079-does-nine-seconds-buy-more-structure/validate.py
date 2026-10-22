"""0079's structure validation: model-long9 vs model-longctx vs 9 s real."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "experiments"))

from crowgpt.gpu import claim

claim()

import numpy as np
import torch

from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import MIN_GRADEABLE_SECONDS
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore
from lib.dustprobe import DUST_THRESHOLD, clip_features

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
SPECIES = "american-crow"
N_DRAWS, N_REAL = 100, 200
SAMPLING = {"temperature": 1.1, "top_k": 200}
ARMS = {
    "model-long9": (HERE / "results" / "model-long9" / "model.pt", 690),
    "model-longctx": (HERE / "results" / "model-longctx" / "model.pt", 460),
}


def stats_of(seg, audio):
    db, fps = seg.envelope(audio, SAMPLE_RATE)
    floor = np.percentile(db, seg.floor_pctl)
    bursts = seg.bursts(db, fps, floor)
    gaps = [(b[0] - a[1]) / fps for a, b in zip(bursts, bursts[1:])]
    return len(bursts), gaps


def describe(rows, feats=()):
    units = np.array([r[0] for r in rows])
    gaps = [g for r in rows for g in r[1]]
    out = {
        "n": len(rows), "mean_units": round(float(units.mean()), 2),
        "single_share": round(float((units <= 1).mean()), 3),
        "gaps_per_clip": round(len(gaps) / len(rows), 2),
        "median_gap_s": round(float(np.median(gaps)), 3) if gaps else None,
    }
    if feats:
        out["dust_rate"] = round(
            float(np.mean([p <= DUST_THRESHOLD for p in feats])), 3)
    return out


def main():
    run = Run("0079 — NINE-SECOND GATE", list(ARMS) + ["real", "verdict"])
    seg, results = Segmenter(), {}
    try:
        for arm, (ckpt, frames) in ARMS.items():
            with run.stage(arm) as stage:
                sampler = Sampler(ckpt, token_dir=None, decoder_state="finetuned")
                rows, feats, seed = [], [], 44_000
                while len(rows) < N_DRAWS and seed < 44_000 + N_DRAWS * 6:
                    flat = sampler.tokens(SPECIES, seed=seed, max_frames=frames,
                                          **SAMPLING)
                    grid = sampler.codec.unflatten(flat)
                    audio = np.asarray(sampler.codec.decode(
                        torch.from_numpy(grid))[0], dtype=np.float32)
                    if audio.size / SAMPLE_RATE >= MIN_GRADEABLE_SECONDS:
                        rows.append(stats_of(seg, audio))
                        f = clip_features(seg, normalise(audio), SAMPLE_RATE)
                        if f:
                            feats.append(f["pitch_strength"])
                    seed += 1
                    stage.update(len(rows), N_DRAWS, extra=f"seed {seed}")
                results[arm] = describe(rows, feats)
                run.note(f"{arm}: {results[arm]}")
                del sampler
                torch.cuda.empty_cache()

        with run.stage("real") as stage:
            store = BoutStore(DATA / "bouts-9s")
            splits = store.split(seed=0)
            seen, rows = set(), []
            for i in splits["test"]:
                r = store.index[i]
                if r["species"] != SPECIES or r["recording_id"] in seen \
                        or r["n_samples"] < SAMPLE_RATE:
                    continue
                seen.add(r["recording_id"])
                rows.append(stats_of(seg, normalise(store.audio(r))))
                if len(rows) >= N_REAL:
                    break
            results["real-9s"] = describe(rows)
            run.note(f"real-9s: {results['real-9s']}")
            stage.update(1, 1)

        with run.stage("verdict") as stage:
            stage.update(1, 1)

        (OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
