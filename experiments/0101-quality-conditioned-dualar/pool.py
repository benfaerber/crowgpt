"""0101, the blinded sitting: Dual-AR 17M q4_crisp (CFG w=1.6) vs CrowGPT2.

Matches 0096's listening pool protocol exactly:
  - 54 trials in 3 doses of 18, 30-minute cooldown, results withheld until all 54
    are answered: 40 comparisons (side-balanced per dose), 8 real catches (4 per
    arm, side-balanced), and 6 swapped-side repeats to measure repeatability.
  - 56 fresh unseen real test groups (48 anchors + 8 catches), disjoint from
    every previously registered pool in field.db.
  - Unseen seed block (101500..), zero quality-based cherry-picking: the first
    44 gradeable (>= 1.0 s) draws per arm.
  - Both arms decode through the 0063 adversarial finetuned decoder.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "crowgpt/src"))
sys.path.insert(0, str(REPO / "experiments"))
sys.path.insert(0, str(REPO / "experiments/0086-can-tuned-training-improve-crowgpt2"))

import numpy as np
import soundfile as sf
import torch

import finish
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import MIN_GRADEABLE_SECONDS
from crowgpt.dualar import DualARSampler
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore
from crowgpt.train import require_device
from training import atomic_json

spec96 = importlib.util.spec_from_file_location(
    "pool_0096", REPO / "experiments/0096-does-longer-training-close-the-gap-to-crowgpt2/pool.py"
)
pool96 = importlib.util.module_from_spec(spec96)
spec96.loader.exec_module(pool96)

POOL_NAME = "quality-0101"
finish.POOL_NAME = POOL_NAME
OUTPUT = REPO / "crowgpt/results/quality-0101"
CLIP_DIR = REPO / "crowgpt/results/listening-pools" / POOL_NAME
POOL_SEED = 101500

ARMS = {
    "crowgpt2": {
        "path": finish.INCUMBENT,
        "dualar": False,
        "sampling": dict(temperature=1.1, top_k=200, max_frames=460),
    },
    "candidate": {
        "path": OUTPUT / "dualar-quality-240k/step-240000.pt",
        "dualar": True,
        "sampling": dict(
            temperature=1.1,
            top_k=200,
            max_frames=460,
            channel="q4_crisp",
            guidance_scale=1.6,
            uncond_channel="q_unknown",
        ),
    },
}


def draw_arm(name, cfg, stage, count=44):
    sampler = (
        DualARSampler(cfg["path"], decoder_state="finetuned", device="cuda")
        if cfg["dualar"]
        else Sampler(cfg["path"], decoder_state="finetuned", device="cuda")
    )
    seg = Segmenter()
    rows, attempts = [], []
    try:
        for seed in range(POOL_SEED, POOL_SEED + count * 10):
            audio = np.asarray(
                sampler.audio("american-crow", seed=seed, **cfg["sampling"]),
                dtype=np.float32,
            )
            if not np.isfinite(audio).all():
                raise ValueError(f"Nonfinite audio seed {seed}")
            secs = audio.size / SAMPLE_RATE
            gradeable = secs >= MIN_GRADEABLE_SECONDS
            attempts.append({"seed": seed, "seconds": secs, "gradeable": gradeable})
            if gradeable:
                normed = normalise(audio)
                row = finish.features(seg, normed) | {"seed": seed}
                filename = f"{name}-{len(rows):02d}.wav"
                sf.write(CLIP_DIR / filename, normed, SAMPLE_RATE, subtype="PCM_16")
                row["file"] = filename
                rows.append(row)
            stage.update(len(rows), count, extra=f"{name} seed {seed}; {len(attempts)} tries")
            if len(rows) == count:
                return {"rows": rows, "attempts": attempts, "summary": finish.describe(rows)}
    finally:
        del sampler
        finish.cleanup()
    raise RuntimeError(f"{name}: only {len(rows)} gradeable clips from {len(attempts)} attempts")


def main():
    if POOL_NAME in dict(finish.pool_specs()):
        print(f"Pool {POOL_NAME} already exists; leaving it untouched")
        return
    if require_device() != "cuda":
        raise RuntimeError("GPU required")

    store = BoutStore(finish.DATA / "crowgpt/bouts-6s")
    run = Run("0101 listening pool", ["pool crowgpt2", "pool candidate", "register"])
    CLIP_DIR.mkdir(parents=True, exist_ok=True)

    drawn = {}
    for arm_name, cfg in ARMS.items():
        with run.stage(f"pool {arm_name}") as stage:
            drawn[arm_name] = draw_arm(arm_name, cfg, stage, count=44)
            run.note(f"{arm_name}: {json.dumps(drawn[arm_name]['summary'])}")

    with run.stage("register") as stage:
        chosen = finish.select_reals(store, n=56, min_seconds=2)
        anchors, catch_reals = [], []
        for n, i in enumerate(chosen):
            filename = f"real-{n:02d}.wav"
            sf.write(
                CLIP_DIR / filename,
                normalise(store.audio(store.index[i])),
                SAMPLE_RATE,
                subtype="PCM_16",
            )
            (anchors if n < 48 else catch_reals).append(filename)

        trials = pool96.Schedule(drawn, anchors, catch_reals, seed=101).trials()
        payload = {
            "name": POOL_NAME,
            "question": finish.QUESTION,
            "clip_dir": str(CLIP_DIR),
            "dose_size": 18,
            "reveal_at": len(trials),
            "trials": trials,
            "spec": {
                "experiment": "0101",
                "candidate": str(ARMS["candidate"]["path"].relative_to(REPO)),
                "candidate_sampling": ARMS["candidate"]["sampling"],
                "incumbent": str(ARMS["crowgpt2"]["path"].relative_to(REPO)),
                "incumbent_sampling": ARMS["crowgpt2"]["sampling"],
                "decoder": "finetuned",
                "seed_base": POOL_SEED,
                "repeats": 6,
                "draws": drawn,
                "anchor_bouts": chosen,
                "anchor_groups": [store.index[i]["group_key"] for i in chosen],
            },
        }
        atomic_json(OUTPUT / "pool.json", payload)

        fs_py = REPO / "fieldserver/.venv/bin/python"
        reg_py = str(fs_py) if fs_py.exists() else sys.executable
        done = subprocess.run(
            [
                reg_py,
                str(REPO / "fieldserver/tools/register_pool.py"),
                str(OUTPUT / "pool.json"),
                "--dose-size", "18",
                "--cooldown", "30",
            ],
            text=True,
            capture_output=True,
        )
        if done.returncode:
            raise RuntimeError(done.stdout + done.stderr)
        run.note(done.stdout.strip())
        atomic_json(
            HERE / "pool_results.json",
            {
                "pool": POOL_NAME,
                "trials": len(trials),
                "dose_size": 18,
                "cooldown_minutes": 30,
                "seed_base": POOL_SEED,
                "arm_summaries": {k: v["summary"] for k, v in drawn.items()},
            },
        )
        stage.update(1, 1, extra=f"{len(trials)} trials registered")
        print(done.stdout.strip())
        print(json.dumps({k: v["summary"] for k, v in drawn.items()}, indent=2))


if __name__ == "__main__":
    main()
