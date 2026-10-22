"""The dust-controlled sitting: longctx at T1.1/k200 vs its own default.

0069's grid says more sampling freedom means less blowing-dust AND better
structure — no tradeoff — but the probe that says so validated marginal
(AUC 0.699), so the candidate default earns its place through the pool or
not at all. Same model both arms, same max_frames, so 0044's length
confound is designed out rather than checked after. Anchors skip the 112
test bouts the two 0067 sittings consumed; seeds sit at 3000, clear of
every recorded range (0067: 0+, sitting2: 1000+, 0070: 9000+, grid: 5000+).
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

from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import MIN_GRADEABLE_SECONDS
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").__dict__["environ"].get("DATA_DIR")
            or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
POOL_NAME = "dust-0069"
CLIP_DIR = HERE / "results" / "listening-pools" / POOL_NAME
SPECIES = "american-crow"
CKPT = HERE / "results" / "model-longctx" / "model.pt"
MAX_FRAMES = 460
ARMS = {"hot": {"temperature": 1.1, "top_k": 200},
        "default": {"temperature": 1.0, "top_k": 200}}
N_COMPARE, N_CATCH, DOSE, COOLDOWN = 40, 8, 20, 30
BLOCK_PLAN = [(17, 3), (17, 3), (6, 2)]
SEED_START = 3000
SKIP_REALS = 112

QUESTION = (
    "Which clip sounds closer to the reference — the whole calling "
    "sequence and the voice itself. Same model both sides, different "
    "sampling. “They are the same” is a real answer. Your per-clip "
    "notes (“1. … 2. …”) were the most useful thing the last sitting "
    "produced — bellows, robo, hoarse, where in the clip it happens."
)


def draws(sampler, params, wanted, stage, label):
    out, seed = [], SEED_START
    while len(out) < wanted and seed < SEED_START + wanted * 6:
        flat = sampler.tokens(SPECIES, seed=seed, max_frames=MAX_FRAMES,
                              **params)
        grid = sampler.codec.unflatten(flat)
        audio = np.asarray(sampler.codec.decode(torch.from_numpy(grid))[0],
                           dtype=np.float32)
        if audio.size / SAMPLE_RATE >= MIN_GRADEABLE_SECONDS:
            out.append({"audio": audio, "seed": seed,
                        "seconds": round(audio.size / SAMPLE_RATE, 2)})
        seed += 1
        stage.update(len(out), wanted, extra=f"{label} seed {seed}")
    return out


def main():
    run = Run("0069 — THE DUST SITTING", ["hot", "default", "real", "pool"])
    try:
        CLIP_DIR.mkdir(parents=True, exist_ok=True)
        sampler = Sampler(CKPT, token_dir=None, decoder_state="finetuned")
        arms = {}
        for name, params in ARMS.items():
            with run.stage(name) as stage:
                arms[name] = draws(sampler, params,
                                   N_COMPARE + N_CATCH // 2, stage, name)

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
            names = {arm: [write(f"{arm}-{n:03d}.wav", c["audio"])
                           for n, c in enumerate(clips)]
                     for arm, clips in arms.items()}
            catch_gens = [("hot", n) for n in names["hot"][N_COMPARE:]] \
                + [("default", n) for n in names["default"][N_COMPARE:]]

            rng = np.random.default_rng(2)
            trials, anchor_it = [], iter(anchors)
            ci = cc = flip_a = flip_r = 0
            for block, (n_cmp, n_cat) in enumerate(BLOCK_PLAN):
                slots = ["c"] * n_cmp + ["k"] * n_cat
                rng.shuffle(slots)
                for s in slots:
                    if s == "c":
                        hot_first = flip_a % 2 == 0
                        flip_a += 1
                        one, two = (names["hot"][ci], names["default"][ci]) \
                            if hot_first else (names["default"][ci], names["hot"][ci])
                        trials.append({
                            "block": block, "kind": "compare",
                            "anchor_clip": next(anchor_it),
                            "first_clip": one, "second_clip": two,
                            "first_arm": "hot" if hot_first else "default",
                            "second_arm": "default" if hot_first else "hot",
                            "facts": {"hot_s": arms["hot"][ci]["seconds"],
                                      "default_s": arms["default"][ci]["seconds"]},
                        })
                        ci += 1
                    else:
                        gen_arm, gen_name = catch_gens[cc]
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
                "spec": {"experiment": "0069 dust sitting",
                         "model": "model-longctx, finetuned decoder, both arms",
                         "arms": ARMS,
                         "hot_seeds": [c["seed"] for c in arms["hot"]],
                         "default_seeds": [c["seed"] for c in arms["default"]],
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
