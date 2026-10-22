"""0070: the control 0069 lacked — round-trips vs generated tokens, both decoders.

Encoding is shared (the finetune never touched the encoder), so each clip
yields one code grid and two decodes, and the paired difference isolates
the decoder exactly. The between-conditions comparison of those paired
differences is the experiment; everything else is bookkeeping.
"""
import json
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

from lib.dustprobe import FEATURES, clip_features, is_dusty
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import MIN_GRADEABLE_SECONDS
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore, codec_from_manifest

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
CKPT = HERE / "results" / "model-longctx" / "model.pt"
SPECIES = "american-crow"
N_PER_CONDITION = 150
PER_RECORDING = 2
SEED_START = 9000
MAX_FRAMES = 460


def main():
    run = Run("0070 — DECODER OFF-DISTRIBUTION",
              ["roundtrip", "generated", "verdict"])
    seg, results = Segmenter(), {}
    deltas = defaultdict(list)
    flips = defaultdict(lambda: [0, 0])
    try:
        sampler = Sampler(CKPT, token_dir=None, decoder_state="finetuned")
        frozen = codec_from_manifest(sampler.manifest, device=sampler.device)
        fine = sampler.codec

        def both(grid, condition):
            grid = torch.from_numpy(grid) if isinstance(grid, np.ndarray) else grid
            a = clip_features(seg, normalise(np.asarray(
                fine.decode(grid)[0], dtype=np.float32)), SAMPLE_RATE)
            b = clip_features(seg, normalise(np.asarray(
                frozen.decode(grid)[0], dtype=np.float32)), SAMPLE_RATE)
            if a and b:
                deltas[condition].append(
                    {f: a[f] - b[f] for f in FEATURES})
                flips[condition][0] += is_dusty(a)
                flips[condition][1] += is_dusty(b)
                return True
            return False

        with run.stage("roundtrip") as stage:
            store = BoutStore(DATA / "bouts-6s")
            splits = store.split(seed=0)
            per_rec, done = defaultdict(int), 0
            for i in splits["test"]:
                r = store.index[i]
                if r["species"] != SPECIES or r["n_samples"] < SAMPLE_RATE \
                        or per_rec[r["recording_id"]] >= PER_RECORDING:
                    continue
                per_rec[r["recording_id"]] += 1
                grid = frozen.encode(normalise(store.audio(r)))
                done += both(grid, "roundtrip")
                stage.update(done, N_PER_CONDITION, extra=f"bout {i}")
                if done >= N_PER_CONDITION:
                    break

        with run.stage("generated") as stage:
            done, seed = 0, SEED_START
            while done < N_PER_CONDITION and seed < SEED_START + N_PER_CONDITION * 6:
                flat = sampler.tokens(SPECIES, seed=seed, max_frames=MAX_FRAMES)
                grid = sampler.codec.unflatten(flat)
                seed += 1
                length = fine.decode(torch.from_numpy(grid))[0].size
                if length / SAMPLE_RATE < MIN_GRADEABLE_SECONDS:
                    continue
                done += both(grid, "generated")
                stage.update(done, N_PER_CONDITION, extra=f"seed {seed}")

        with run.stage("verdict") as stage:
            from scipy.stats import mannwhitneyu, wilcoxon

            for condition, rows in deltas.items():
                pitch = [r["pitch_strength"] for r in rows]
                results[condition] = {
                    "n": len(rows),
                    "mean_delta": {f: round(float(np.mean(
                        [r[f] for r in rows])), 4) for f in FEATURES},
                    "wilcoxon_p_pitch": round(float(wilcoxon(pitch).pvalue), 5),
                    "dusty_finetuned": flips[condition][0],
                    "dusty_frozen": flips[condition][1],
                }
                run.note(f"{condition}: {results[condition]}")
            results["between_conditions_mw_p_pitch"] = round(float(mannwhitneyu(
                [r["pitch_strength"] for r in deltas["roundtrip"]],
                [r["pitch_strength"] for r in deltas["generated"]]).pvalue), 5)
            stage.update(1, 1)

        (OUT / "results.json").write_text(json.dumps(results, indent=2))
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
