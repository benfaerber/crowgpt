"""0072: positional periodicity — does generated voice fade where real holds?

Per burst, ordered in time: pitch strength from lib/dustprobe. The per-clip
statistic is late-minus-early (second half of bursts vs first), real 6 s
bouts as the control that licenses everything else. All audio decodes
through the finetuned decoder — 0070 bans cross-decoder comparison, and
every cell here is within it.
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(REPO / "experiments"))

from crowgpt.gpu import claim

claim()

import numpy as np
import torch
from scipy.stats import wilcoxon

from lib.dustprobe import MIN_BURST_S, bursts_of, pitch_strength
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import MIN_GRADEABLE_SECONDS
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore

DATA = Path(os.environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
SPECIES = "american-crow"
N_DRAWS, N_REAL, PER_RECORDING = 150, 200, 2
SEED_START = 20000
ARMS = {
    "longctx-T1.0": (HERE / "results" / "model-longctx" / "model.pt", 460,
                     {"temperature": 1.0, "top_k": 200}),
    "longctx-T1.1": (HERE / "results" / "model-longctx" / "model.pt", 460,
                     {"temperature": 1.1, "top_k": 200}),
    "units-3s": (HERE / "results" / "model-units" / "model.pt", 230,
                 {"temperature": 1.0, "top_k": 200}),
}


def profile(seg, audio):
    """Per-burst pitch strengths in time order, or None below two bursts."""
    strengths = [pitch_strength(b, SAMPLE_RATE)
                 for b in bursts_of(seg, audio, SAMPLE_RATE)]
    if len(strengths) < 2:
        return None
    half = len(strengths) // 2
    early, late = strengths[: half], strengths[half:]
    return {
        "n_bursts": len(strengths),
        "seconds": audio.size / SAMPLE_RATE,
        "early": float(np.mean(early)),
        "late": float(np.mean(late)),
        "delta": float(np.mean(late) - np.mean(early)),
        "strengths": [round(s, 4) for s in strengths],
    }


def describe(rows):
    deltas = np.array([r["delta"] for r in rows])
    per_sec = np.array([r["delta"] / r["seconds"] for r in rows])
    return {
        "n": len(rows),
        "mean_delta": round(float(deltas.mean()), 4),
        "mean_delta_per_sec": round(float(per_sec.mean()), 4),
        "declining_share": round(float((deltas < 0).mean()), 3),
        "wilcoxon_p": round(float(wilcoxon(deltas).pvalue), 5) if len(rows) > 5 else None,
        "mean_early": round(float(np.mean([r["early"] for r in rows])), 4),
        "mean_late": round(float(np.mean([r["late"] for r in rows])), 4),
    }


def by_ordinal(rows, upto=8):
    """Mean pitch strength at each burst position, across clips that reach it."""
    out = {}
    for k in range(upto):
        values = [r["strengths"][k] for r in rows if len(r["strengths"]) > k]
        if len(values) >= 20:
            out[f"burst_{k + 1}"] = {"n": len(values),
                                     "mean": round(float(np.mean(values)), 4)}
    return out


def main():
    run = Run("0072 — VOICE DECAY", list(ARMS) + ["real", "verdict"])
    seg, rows, results = Segmenter(), {}, {}
    try:
        for arm, (ckpt, frames, params) in ARMS.items():
            with run.stage(arm) as stage:
                sampler = Sampler(ckpt, token_dir=None, decoder_state="finetuned")
                kept, seed = [], SEED_START
                while len(kept) < N_DRAWS and seed < SEED_START + N_DRAWS * 8:
                    flat = sampler.tokens(SPECIES, seed=seed, max_frames=frames,
                                          **params)
                    grid = sampler.codec.unflatten(flat)
                    audio = np.asarray(sampler.codec.decode(
                        torch.from_numpy(grid))[0], dtype=np.float32)
                    seed += 1
                    if audio.size / SAMPLE_RATE < MIN_GRADEABLE_SECONDS:
                        continue
                    p = profile(seg, normalise(audio))
                    if p:
                        kept.append(p)
                    stage.update(len(kept), N_DRAWS, extra=f"seed {seed}")
                rows[arm] = kept
                results[arm] = describe(kept)
                run.note(f"{arm}: {results[arm]}")
                del sampler
                torch.cuda.empty_cache()

        with run.stage("real") as stage:
            store = BoutStore(DATA / "bouts-6s")
            splits = store.split(seed=0)
            per_rec, kept = defaultdict(int), []
            for i in splits["test"]:
                r = store.index[i]
                if r["species"] != SPECIES or r["n_samples"] < SAMPLE_RATE \
                        or per_rec[r["recording_id"]] >= PER_RECORDING:
                    continue
                per_rec[r["recording_id"]] += 1
                p = profile(seg, normalise(store.audio(r)))
                if p:
                    kept.append(p)
                if len(kept) >= N_REAL:
                    break
            rows["real"] = kept
            results["real"] = describe(kept)
            run.note(f"real: {results['real']}")
            stage.update(1, 1)

        with run.stage("verdict") as stage:
            results["by_ordinal"] = {arm: by_ordinal(r) for arm, r in rows.items()}
            stage.update(1, 1)

        (OUT / "results.json").write_text(json.dumps(results, indent=2))
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
