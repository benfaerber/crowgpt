"""0066's gate: unit-count distributions, no ears.

Three arms through 0024's instrument (the segmenter at its validated 12 dB —
the same numerics that measured the defect and that wrote the training
signal): ~100 draws from model-units, ~100 from model-v3-scrape (its
unconditioned twin on the same corpus, the control), and the real held-out
bouts. The question is whether the generated unit distribution moved toward
real's; 0024's baseline was 1.37 generated against 3.37 real, 70% single-caw.

Draws are by seed order, ≥1 s, decoded through the finetuned decoder — the
same conditions every measurement now runs under.
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
N_DRAWS = 100
N_REAL = 200
ARMS = {
    "model-units": HERE / "results" / "model-units" / "model.pt",
    "model-v3-scrape": HERE / "results" / "model-v3-scrape" / "model.pt",
}


def units_of(segmenter, audio):
    db, fps = segmenter.envelope(audio, SAMPLE_RATE)
    floor = np.percentile(db, segmenter.floor_pctl)
    return len(segmenter.bursts(db, fps, floor))


def describe(counts):
    counts = np.array(counts)
    return {
        "n": len(counts),
        "mean": round(float(counts.mean()), 2),
        "median": float(np.median(counts)),
        "single_share": round(float((counts <= 1).mean()), 3),
        "distribution": {str(k): int((counts == k).sum())
                         for k in range(0, min(10, counts.max() + 1))},
    }


def main():
    run = Run("0066 — UNIT GATE", list(ARMS) + ["real", "verdict"])
    segmenter = Segmenter()
    results = {}
    counts = {}
    try:
        for arm, checkpoint in ARMS.items():
            with run.stage(arm) as stage:
                sampler = Sampler(checkpoint, token_dir=None,
                                  decoder_state="finetuned")
                arm_counts, seed = [], 0
                while len(arm_counts) < N_DRAWS and seed < N_DRAWS * 6:
                    flat = sampler.tokens(SPECIES, seed=seed)
                    grid = sampler.codec.unflatten(flat)
                    audio = np.asarray(
                        sampler.codec.decode(torch.from_numpy(grid))[0],
                        dtype=np.float32)
                    if audio.size / SAMPLE_RATE >= MIN_GRADEABLE_SECONDS:
                        arm_counts.append(units_of(segmenter, audio))
                    seed += 1
                    stage.update(len(arm_counts), N_DRAWS, extra=f"seed {seed}")
                counts[arm] = arm_counts
                results[arm] = describe(arm_counts)
                run.note(f"{arm}: mean {results[arm]['mean']} · "
                         f"single-caw {results[arm]['single_share']}")
                del sampler
                torch.cuda.empty_cache()

        with run.stage("real") as stage:
            store = BoutStore(DATA / "bouts")
            splits = store.split(seed=0)
            seen, real_counts = set(), []
            for i in splits["test"]:
                row = store.index[i]
                if row["species"] != SPECIES or row["recording_id"] in seen \
                        or row["n_samples"] < SAMPLE_RATE * MIN_GRADEABLE_SECONDS:
                    continue
                seen.add(row["recording_id"])
                real_counts.append(units_of(segmenter, normalise(store.audio(row))))
                if len(real_counts) >= N_REAL:
                    break
                stage.update(len(real_counts), N_REAL)
            counts["real"] = real_counts
            results["real"] = describe(real_counts)
            run.note(f"real: mean {results['real']['mean']} · "
                     f"single-caw {results['real']['single_share']}")

        with run.stage("verdict") as stage:
            from scipy.stats import mannwhitneyu

            for pair in (("model-units", "real"), ("model-units", "model-v3-scrape"),
                         ("model-v3-scrape", "real")):
                stat = mannwhitneyu(counts[pair[0]], counts[pair[1]],
                                    alternative="two-sided")
                results[f"mw_{pair[0]}_vs_{pair[1]}"] = round(float(stat.pvalue), 5)
            stage.update(1, 1)

        (OUT / "results.json").write_text(json.dumps(results, indent=2))
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
