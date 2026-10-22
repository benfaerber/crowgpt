"""The voice sitting: model-calltype vs the b32 candidate, as chat serves them.

Each arm draws conditioned on the four call types at its own serving cell —
this is a comparison of products, not of matched laboratory conditions, and
the length difference that implies (3 s vs 6 s windows) is recorded per trial
for the 0044 length check rather than designed away, because the length IS
part of what chat serves. Requested types are hidden from the grader and
carried in facts.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

import numpy as np
import soundfile as sf
import torch

from crowgpt.calltype import CORE
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import MIN_GRADEABLE_SECONDS
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
POOL_NAME = "voice-0078"
CLIP_DIR = HERE / "results" / "listening-pools" / POOL_NAME
SPECIES = "american-crow"
ARMS = {
    "calltype": {"ckpt": HERE / "results" / "model-calltype" / "model.pt",
                 "temperature": 1.0, "max_frames": 225},
    "b32": {"ckpt": HERE / "results" / "model-longctx-ct-b32" / "model.pt",
            "temperature": 1.1, "max_frames": 460},
}
PER_TYPE_COMPARE, PER_TYPE_CATCH = 10, 2
N_COMPARE = PER_TYPE_COMPARE * len(CORE)          # 40
N_CATCH = PER_TYPE_CATCH * len(CORE)              # 8
DOSE, COOLDOWN = 16, 30
BLOCK_PLAN = [(13, 3), (13, 3), (14, 2)]          # 48 = 3 doses of 16, no tail
SEED_BASE = 43_000
SEED_STRIDE = 200                                  # per-type seed block
SKIP_REALS = 168

QUESTION = (
    "Which clip sounds more like a real crow — the voice itself, not the "
    "pattern. Different models, each serving what the chat buttons serve. "
    "“They are the same” is a real answer. Per-clip notes (“1. … 2. …”) are "
    "the most valuable thing you produce — human-ish, froggy, metallic, "
    "alien, hoarse, where in the clip it happens."
)


def draws(sampler, arm, stage):
    """Per call type: PER_TYPE_COMPARE + half the catches, gradeable-length."""
    out = {}
    wanted = PER_TYPE_COMPARE + PER_TYPE_CATCH // 2
    for t, call_type in enumerate(CORE):
        clips, seed = [], SEED_BASE + t * SEED_STRIDE
        while len(clips) < wanted and seed < SEED_BASE + (t + 1) * SEED_STRIDE:
            audio = sampler.audio(SPECIES, call_type=call_type, seed=seed,
                                  temperature=arm["temperature"], top_k=200,
                                  max_frames=arm["max_frames"])
            if audio.size / SAMPLE_RATE >= MIN_GRADEABLE_SECONDS:
                clips.append({"audio": audio, "seed": seed,
                              "call_type": call_type,
                              "seconds": round(audio.size / SAMPLE_RATE, 2)})
            seed += 1
            stage.update(t * wanted + len(clips), len(CORE) * wanted,
                         extra=f"{call_type} seed {seed}")
        if len(clips) < wanted:
            raise RuntimeError(f"could not draw {wanted} gradeable "
                               f"{call_type} clips")
        out[call_type] = clips
    return out


def main():
    run = Run("0078 — THE VOICE SITTING", list(ARMS) + ["real", "pool"])
    try:
        CLIP_DIR.mkdir(parents=True, exist_ok=True)
        arms = {}
        for name, arm in ARMS.items():
            with run.stage(name) as stage:
                sampler = Sampler(arm["ckpt"], decoder_state="finetuned")
                arms[name] = draws(sampler, arm, stage)
                del sampler
                torch.cuda.empty_cache()

        with run.stage("real") as stage:
            store = BoutStore(DATA / "bouts-6s")
            splits = store.split(seed=0)
            seen, reals, skipped = set(), [], 0
            for i in splits["test"]:
                r = store.index[i]
                if r["species"] != SPECIES or r["recording_id"] in seen \
                        or r["n_samples"] < SAMPLE_RATE * 2:
                    continue
                seen.add(r["recording_id"])
                if skipped < SKIP_REALS:
                    skipped += 1
                    continue
                reals.append({"audio": normalise(store.audio(r)), "bout": i})
                if len(reals) >= N_COMPARE + 2 * N_CATCH:
                    break
            if len(reals) < N_COMPARE + 2 * N_CATCH:
                raise RuntimeError(
                    f"only {len(reals)} fresh real bouts after skipping "
                    f"{SKIP_REALS} — widen the split before registering")
            stage.update(1, 1)

        def write(name, audio):
            sf.write(CLIP_DIR / name, np.asarray(audio, dtype=np.float32),
                     SAMPLE_RATE, subtype="PCM_16")
            return name

        with run.stage("pool") as stage:
            anchors = [write(f"anchor-{n:02d}.wav", r["audio"])
                       for n, r in enumerate(reals[: N_COMPARE + N_CATCH])]
            catch_reals = [write(f"real-{n:02d}.wav", r["audio"])
                           for n, r in enumerate(reals[N_COMPARE + N_CATCH:])]

            compares, catches = [], []
            for call_type in CORE:
                slug = call_type.replace(" ", "-")
                a = arms["calltype"][call_type]
                b = arms["b32"][call_type]
                for k in range(PER_TYPE_COMPARE):
                    compares.append({
                        "call_type": call_type,
                        "calltype": write(f"calltype-{slug}-{k:02d}.wav",
                                          a[k]["audio"]),
                        "b32": write(f"b32-{slug}-{k:02d}.wav", b[k]["audio"]),
                        "calltype_s": a[k]["seconds"], "b32_s": b[k]["seconds"],
                    })
                for k in range(PER_TYPE_CATCH // 2):
                    idx = PER_TYPE_COMPARE + k
                    catches.append(("calltype", write(
                        f"catch-calltype-{slug}-{k}.wav", a[idx]["audio"])))
                    catches.append(("b32", write(
                        f"catch-b32-{slug}-{k}.wav", b[idx]["audio"])))

            rng = np.random.default_rng(78)
            rng.shuffle(compares)
            rng.shuffle(catches)

            trials, anchor_it = [], iter(anchors)
            ci = cc = flip_a = flip_r = 0
            for block, (n_cmp, n_cat) in enumerate(BLOCK_PLAN):
                slots = ["c"] * n_cmp + ["k"] * n_cat
                rng.shuffle(slots)
                for s in slots:
                    if s == "c":
                        row = compares[ci]
                        calltype_first = flip_a % 2 == 0
                        flip_a += 1
                        one, two = (row["calltype"], row["b32"]) \
                            if calltype_first else (row["b32"], row["calltype"])
                        trials.append({
                            "block": block, "kind": "compare",
                            "anchor_clip": next(anchor_it),
                            "first_clip": one, "second_clip": two,
                            "first_arm": "calltype" if calltype_first else "b32",
                            "second_arm": "b32" if calltype_first else "calltype",
                            "facts": {"call_type": row["call_type"],
                                      "calltype_s": row["calltype_s"],
                                      "b32_s": row["b32_s"]},
                        })
                        ci += 1
                    else:
                        gen_arm, gen_name = catches[cc]
                        real_first = flip_r % 2 == 0
                        flip_r += 1
                        one, two = (catch_reals[cc], gen_name) if real_first \
                            else (gen_name, catch_reals[cc])
                        trials.append({
                            "block": block, "kind": "catch",
                            "anchor_clip": next(anchor_it),
                            "first_clip": one, "second_clip": two,
                            "first_arm": "real" if real_first else gen_arm,
                            "second_arm": gen_arm if real_first else "real",
                        })
                        cc += 1

            payload = {
                "name": POOL_NAME, "question": QUESTION,
                "clip_dir": str(CLIP_DIR), "trials": trials,
                "spec": {"experiment": "0078 voice sitting",
                         "arms": {n: {"ckpt": str(a["ckpt"]),
                                      "temperature": a["temperature"],
                                      "max_frames": a["max_frames"]}
                                  for n, a in ARMS.items()},
                         "decoder": "finetuned, both arms",
                         "seed_base": SEED_BASE, "seed_stride": SEED_STRIDE,
                         "anchor_bouts": [r["bout"] for r in reals]},
            }
            pool_json = OUT / "pool.json"
            pool_json.write_text(json.dumps(payload, indent=2))
            result = subprocess.run(
                [str(REPO / "fieldserver" / ".venv" / "bin" / "python"),
                 str(REPO / "fieldserver" / "tools" / "register_pool.py"),
                 str(pool_json), "--dose-size", str(DOSE),
                 "--cooldown", str(COOLDOWN)],
                capture_output=True, text=True)
            stage.say(result.stdout.strip() or result.stderr.strip())
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip())
            run.note(f"pool {POOL_NAME}: {len(trials)} trials, dose {DOSE}, "
                     f"cooldown {COOLDOWN} min — on the dashboard")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print("registered", POOL_NAME)


if __name__ == "__main__":
    main()
