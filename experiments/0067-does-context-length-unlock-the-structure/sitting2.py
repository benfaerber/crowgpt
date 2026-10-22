"""The second 0067 sitting: same question, fresh clips, tags that now ask.

Ben offered a more careful grading pass after 0068's null returned the
verdict to his ear. This is NOT a reopening of longctx-0067 — answers
upsert on trial id, so regrading that pool would overwrite the recorded
first sitting. Same design instead (40 compares + 8 catches, anchored,
doses of 20), drawn from fresh seeds and fresh anchor bouts, graded under
the new tag prompting: ties ask what kept either clip from winning, ±2s
ask what the worse clip did, and "ghost" is in the vocabulary. The two
sittings pool to n=96 on the preference question; the tags are the real
cargo — words for the ghost.
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

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
POOL_NAME = "longctx-0067b"
CLIP_DIR = HERE / "results" / "listening-pools" / POOL_NAME
SPECIES = "american-crow"
ARMS = {
    "model-longctx": (HERE / "results" / "model-longctx" / "model.pt", 460),
    "model-units": (HERE / "results" / "model-units" / "model.pt", 230),
}
N_COMPARE, N_CATCH, DOSE, COOLDOWN = 40, 8, 20, 30
BLOCK_PLAN = [(17, 3), (17, 3), (6, 2)]
#: Fresh material, enforced rather than hoped: generation seeds start past
#: anything the first sitting's spec recorded, and the first SKIP_REALS
#: qualifying test bouts — the ones sitting.py consumed — are skipped.
SEED_START = 1000
SKIP_REALS = 56

QUESTION = (
    "Which clip sounds closer to the reference — as a whole <strong>calling "
    "sequence</strong>: the rhythm, the spacing between caws, the way a real "
    "session unfolds, as well as the voice itself. Clips differ in length by "
    "design; judge the crow, not the clock. “They are the same” is a real "
    "answer — and when it is your answer, or the gap is a ±2, say why with "
    "the tags."
)


def draws(arm, ckpt, frames, wanted, stage):
    sampler = Sampler(ckpt, token_dir=None, decoder_state="finetuned")
    out, seed = [], SEED_START
    while len(out) < wanted and seed < SEED_START + wanted * 6:
        flat = sampler.tokens(SPECIES, seed=seed, max_frames=frames)
        grid = sampler.codec.unflatten(flat)
        audio = np.asarray(sampler.codec.decode(torch.from_numpy(grid))[0],
                           dtype=np.float32)
        if audio.size / SAMPLE_RATE >= MIN_GRADEABLE_SECONDS:
            out.append({"audio": audio, "seed": seed,
                        "seconds": round(audio.size / SAMPLE_RATE, 2)})
        seed += 1
        stage.update(len(out), wanted, extra=f"{arm} seed {seed}")
    del sampler
    torch.cuda.empty_cache()
    return out


def main():
    run = Run("0067 — THE SECOND SITTING", ["longctx", "units", "real", "pool"])
    try:
        CLIP_DIR.mkdir(parents=True, exist_ok=True)
        with run.stage("longctx") as stage:
            a = draws("model-longctx", *ARMS["model-longctx"],
                      N_COMPARE + N_CATCH // 2, stage)
        with run.stage("units") as stage:
            b = draws("model-units", *ARMS["model-units"],
                      N_COMPARE + N_CATCH // 2, stage)

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
                    f"{SKIP_REALS} — test split too small for a second sitting")
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
            a_names = [write(f"longctx-{n:03d}.wav", c["audio"])
                       for n, c in enumerate(a)]
            b_names = [write(f"units-{n:03d}.wav", c["audio"])
                       for n, c in enumerate(b)]
            catch_gens = [("model-longctx", n) for n in a_names[N_COMPARE:]] \
                + [("model-units", n) for n in b_names[N_COMPARE:]]

            rng = np.random.default_rng(1)
            trials, anchor_it = [], iter(anchors)
            ci = cc = flip_a = flip_r = 0
            for block, (n_cmp, n_cat) in enumerate(BLOCK_PLAN):
                slots = ["c"] * n_cmp + ["k"] * n_cat
                rng.shuffle(slots)
                for s in slots:
                    if s == "c":
                        first_a = flip_a % 2 == 0
                        flip_a += 1
                        one, two = (a_names[ci], b_names[ci]) if first_a \
                            else (b_names[ci], a_names[ci])
                        trials.append({
                            "block": block, "kind": "compare",
                            "anchor_clip": next(anchor_it),
                            "first_clip": one, "second_clip": two,
                            "first_arm": "model-longctx" if first_a else "model-units",
                            "second_arm": "model-units" if first_a else "model-longctx",
                            "facts": {"longctx_s": a[ci]["seconds"],
                                      "units_s": b[ci]["seconds"]},
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
                "spec": {"experiment": "0067, second sitting",
                         "decoder": "finetuned (0063), both arms",
                         "longctx_seeds": [c["seed"] for c in a],
                         "units_seeds": [c["seed"] for c in b],
                         "anchor_bouts": [r["bout"] for r in reals]},
            }
            pool_json = OUT / "pool2.json"
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
