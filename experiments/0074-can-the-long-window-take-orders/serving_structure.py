"""Post-hoc supplement, labelled as such: structure under the SERVING condition.

run.py's structure arm drew the conditioned model with its default prefix —
the "unknown" token — because that is the drop-in analogue of an unconditioned
draw. But chat never asks for unknown: every button is a specific type. If the
structure regression lives in the unknown bucket rather than in the conditioned
draws, the gate measured a condition the worker will never serve.

Same seeds as run.py's judge stage, so these are the very clips the head
scored; alarm is the serving-relevant row.
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

from crowgpt.calltype import CORE
from crowgpt.codec import SAMPLE_RATE
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter

sys.path.insert(0, str(REPO / "experiments"))
from lib.dustprobe import DUST_THRESHOLD, clip_features  # noqa: E402

OUT = Path(__file__).resolve().parent
PER_TYPE = 60
SAMPLING = {"temperature": 1.1, "top_k": 200, "max_frames": 460}


def stats_of(seg, audio):
    db, fps = seg.envelope(audio, SAMPLE_RATE)
    floor = np.percentile(db, seg.floor_pctl)
    bursts = seg.bursts(db, fps, floor)
    gaps = [(b[0] - a[1]) / fps for a, b in zip(bursts, bursts[1:])]
    return len(bursts), gaps


def describe(rows, feats):
    units = np.array([r[0] for r in rows])
    gaps = [g for r in rows for g in r[1]]
    return {
        "n": len(rows), "mean_units": round(float(units.mean()), 2),
        "single_share": round(float((units <= 1).mean()), 3),
        "gaps_per_clip": round(len(gaps) / len(rows), 2),
        "median_gap_s": round(float(np.median(gaps)), 3) if gaps else None,
        "dust_rate": round(float(np.mean(
            [p <= DUST_THRESHOLD for p in feats])), 3) if feats else None,
    }


def main():
    run = Run("0074 — SERVING-CONDITION STRUCTURE", ["draw"])
    seg = Segmenter()
    sampler = Sampler(HERE / "results" / "model-longctx-ct" / "model.pt",
                      decoder_state="finetuned")
    results = {}
    with run.stage("draw") as stage:
        done = 0
        for call_type in CORE:
            rows, feats = [], []
            for i in range(PER_TYPE):
                audio = sampler.audio("american-crow", call_type=call_type,
                                      seed=41_000 + i, **SAMPLING)
                rows.append(stats_of(seg, audio))
                f = clip_features(seg, audio, SAMPLE_RATE)
                if f:
                    feats.append(f["pitch_strength"])
                done += 1
                stage.update(done, len(CORE) * PER_TYPE, extra=call_type)
            results[call_type] = describe(rows, feats)
            run.note(f"{call_type}: {results[call_type]}")
    del sampler
    torch.cuda.empty_cache()
    (OUT / "serving_structure.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
