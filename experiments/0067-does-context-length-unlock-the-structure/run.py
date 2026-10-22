"""0067's gate: does a 6 s window buy sequence structure, without ears?

Arms: model-longctx (6 s corpus, recipe-matched batch 16) vs model-units
(the 3 s twin) vs REAL 6 s bouts from bouts-6s' own test split — the
reference moves with the cap or the comparison is a category error. All
generated audio decodes through the finetuned decoder. Instruments are
0024's segmenter numerics: units per bout, single-caw share, mean — plus
the statistic only a longer window can improve: INTER-BURST GAPS (median
gap and gap-count per clip), the rhythm between calls.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

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

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
SPECIES = "american-crow"
N_DRAWS, N_REAL = 100, 200
ARMS = {
    "model-longctx": (HERE / "results" / "model-longctx" / "model.pt", 460),
    "model-units": (HERE / "results" / "model-units" / "model.pt", 230),
}


def stats_of(segmenter, audio):
    db, fps = segmenter.envelope(audio, SAMPLE_RATE)
    floor = np.percentile(db, segmenter.floor_pctl)
    bursts = segmenter.bursts(db, fps, floor)
    gaps = [(b[0] - a[1]) / fps for a, b in zip(bursts, bursts[1:])]
    return len(bursts), gaps


def describe(rows):
    units = np.array([r[0] for r in rows])
    gaps = [g for r in rows for g in r[1]]
    return {
        "n": len(rows), "mean_units": round(float(units.mean()), 2),
        "single_share": round(float((units <= 1).mean()), 3),
        "gaps_per_clip": round(len(gaps) / len(rows), 2),
        "median_gap_s": round(float(np.median(gaps)), 3) if gaps else None,
    }


def main():
    run = Run("0067 — LONG-CONTEXT GATE", list(ARMS) + ["real", "verdict"])
    seg, results, raw = Segmenter(), {}, {}
    try:
        for arm, (ckpt, frames) in ARMS.items():
            with run.stage(arm) as stage:
                sampler = Sampler(ckpt, token_dir=None, decoder_state="finetuned")
                rows, seed = [], 0
                while len(rows) < N_DRAWS and seed < N_DRAWS * 6:
                    flat = sampler.tokens(SPECIES, seed=seed, max_frames=frames)
                    grid = sampler.codec.unflatten(flat)
                    audio = np.asarray(sampler.codec.decode(
                        torch.from_numpy(grid))[0], dtype=np.float32)
                    if audio.size / SAMPLE_RATE >= MIN_GRADEABLE_SECONDS:
                        rows.append(stats_of(seg, audio))
                    seed += 1
                    stage.update(len(rows), N_DRAWS, extra=f"seed {seed}")
                raw[arm], results[arm] = rows, describe(rows)
                run.note(f"{arm}: {results[arm]}")
                del sampler
                torch.cuda.empty_cache()

        with run.stage("real") as stage:
            store = BoutStore(DATA / "bouts-6s")
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
            raw["real"], results["real"] = rows, describe(rows)
            run.note(f"real-6s: {results['real']}")
            stage.update(1, 1)

        with run.stage("verdict") as stage:
            from scipy.stats import mannwhitneyu

            for a, b in (("model-longctx", "real"), ("model-longctx", "model-units"),
                         ("model-units", "real")):
                results[f"mw_units_{a}_vs_{b}"] = round(float(mannwhitneyu(
                    [r[0] for r in raw[a]], [r[0] for r in raw[b]]).pvalue), 5)
            stage.update(1, 1)

        (OUT / "results.json").write_text(json.dumps(results, indent=2))
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
