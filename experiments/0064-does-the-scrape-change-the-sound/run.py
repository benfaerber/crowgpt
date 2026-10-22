"""The 0064 sitting: v3 (scraped corpus) against v2, through the listening-pool
system — doses of 20 from the dashboard's Listening panel, 30-minute cooldown,
graded -2..+2 with defect tags, answers stored server-side.

An earlier version of this script built a standalone PairPage for the same
question; it was replaced the same morning it shipped, because the field
server's pool system already existed and is the stronger instrument (graded
response, per-trial real anchors, defect vocabulary, reveal threshold).
Two instruments for one sitting is the two-vocabularies rot CLAUDE.md warns
about, so the page was retired before it collected an answer.

Both predictions are in the README, written before the build ran.

FAIRNESS RULES, both load-bearing:
  - BOTH ARMS DECODE THROUGH THE FINETUNED DECODER (0063, ear-confirmed).
    The decoder is a shared vocoder, not part of either arm.
  - THE VAL LOSSES ARE NOT COMPARABLE and appear nowhere: v3's 4.82 and
    v2's 4.59 sit on different corpora's val splits.

POOL SHAPE, following churn-spread-0053's conventions: 60 trials in three
balanced blocks of 20 — 50 compares (v3 vs v2, first-arm balanced within
every block) and 10 catches (raw real against a generated clip, real side
alternating). Every trial carries its own raw real anchor. Draws are by seed
order, uncurated, seeds in the pool spec.
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

POOL_NAME = "scrape-v3-0064"
CLIP_DIR = HERE / "results" / "listening-pools" / POOL_NAME
SPECIES = "american-crow"
ARMS = {
    "v3-scrape": HERE / "results" / "model-v3-scrape" / "model.pt",
    "v2-fair-k8": HERE / "results" / "model-fair-k8" / "model.pt",
}
N_COMPARE = 50
N_CATCH = 10
DOSE = 20
COOLDOWN_MIN = 30
BLOCK_PLAN = [(17, 3), (17, 3), (16, 4)]  # (compares, catches) per block

QUESTION = (
    "Which clip sounds closer to the reference recording? Judge the "
    "<strong>timbre</strong> — how much it sounds like a real crow's voice — "
    "not the length and not how many caws it has. “They are the same” "
    "is a real answer; use it whenever you cannot tell."
)


def draws(arm, checkpoint, wanted, stage):
    sampler = Sampler(checkpoint, token_dir=None, decoder_state="finetuned")
    clips, seed = [], 0
    while len(clips) < wanted and seed < wanted * 6:
        flat = sampler.tokens(SPECIES, seed=seed)
        grid = sampler.codec.unflatten(flat)
        audio = np.asarray(sampler.codec.decode(torch.from_numpy(grid))[0],
                           dtype=np.float32)
        if audio.size / SAMPLE_RATE >= MIN_GRADEABLE_SECONDS:
            clips.append({"audio": audio, "arm": arm, "seed": seed})
        seed += 1
        stage.update(len(clips), wanted, extra=f"{arm} seed {seed}")
    del sampler
    torch.cuda.empty_cache()
    return clips


def real_clips(store, wanted):
    splits = store.split(seed=0)
    seen, clips = set(), []
    for i in splits["test"]:
        row = store.index[i]
        if row["species"] != SPECIES or row["recording_id"] in seen \
                or row["n_samples"] < SAMPLE_RATE * MIN_GRADEABLE_SECONDS:
            continue
        seen.add(row["recording_id"])
        clips.append({"audio": normalise(store.audio(row)), "bout": i})
        if len(clips) >= wanted:
            break
    return clips


def write_clip(name, audio):
    sf.write(CLIP_DIR / name, np.asarray(audio, dtype=np.float32),
             SAMPLE_RATE, subtype="PCM_16")
    return name


def main():
    run = Run("0064 — THE V3 SITTING (POOL)", ["v3", "v2", "real", "pool"])
    try:
        CLIP_DIR.mkdir(parents=True, exist_ok=True)
        with run.stage("v3") as stage:
            v3 = draws("v3-scrape", ARMS["v3-scrape"], N_COMPARE + N_CATCH // 2, stage)
        with run.stage("v2") as stage:
            v2 = draws("v2-fair-k8", ARMS["v2-fair-k8"], N_COMPARE + N_CATCH // 2, stage)
        with run.stage("real") as stage:
            store = BoutStore(DATA / "bouts")
            reals = real_clips(store, N_COMPARE + N_CATCH + N_CATCH)
            stage.update(1, 1)

        with run.stage("pool") as stage:
            rng = np.random.default_rng(0)
            anchors = [write_clip(f"real-{n:03d}.wav", c["audio"])
                       for n, c in enumerate(reals[: N_COMPARE + N_CATCH])]
            catch_reals = [write_clip(f"real-{100 + n:03d}.wav", c["audio"])
                           for n, c in enumerate(reals[N_COMPARE + N_CATCH:])]
            v3_names = [write_clip(f"v3-scrape-{n:03d}.wav", c["audio"])
                        for n, c in enumerate(v3)]
            v2_names = [write_clip(f"v2-fair-k8-{n:03d}.wav", c["audio"])
                        for n, c in enumerate(v2)]

            compares = list(zip(v3_names[:N_COMPARE], v2_names[:N_COMPARE]))
            catch_gens = [("v3-scrape", name) for name in v3_names[N_COMPARE:]] \
                + [("v2-fair-k8", name) for name in v2_names[N_COMPARE:]]

            trials, anchor_iter = [], iter(anchors)
            compare_n = catch_n = 0
            v3_first_toggle = real_first_toggle = 0
            for block, (n_cmp, n_cat) in enumerate(BLOCK_PLAN):
                slots = ["compare"] * n_cmp + ["catch"] * n_cat
                rng.shuffle(slots)
                for slot in slots:
                    if slot == "compare":
                        a, b = compares[compare_n]
                        first_v3 = v3_first_toggle % 2 == 0
                        v3_first_toggle += 1
                        trials.append({
                            "block": block, "kind": "compare",
                            "anchor_clip": next(anchor_iter),
                            "first_clip": a if first_v3 else b,
                            "second_clip": b if first_v3 else a,
                            "first_arm": "v3-scrape" if first_v3 else "v2-fair-k8",
                            "second_arm": "v2-fair-k8" if first_v3 else "v3-scrape",
                        })
                        compare_n += 1
                    else:
                        gen_arm, gen_name = catch_gens[catch_n]
                        real_name = catch_reals[catch_n]
                        real_first = real_first_toggle % 2 == 0
                        real_first_toggle += 1
                        trials.append({
                            "block": block, "kind": "catch",
                            "anchor_clip": next(anchor_iter),
                            "first_clip": real_name if real_first else gen_name,
                            "second_clip": gen_name if real_first else real_name,
                            "first_arm": "real" if real_first else gen_arm,
                            "second_arm": gen_arm if real_first else "real",
                        })
                        catch_n += 1

            payload = {
                "name": POOL_NAME,
                "question": QUESTION,
                "clip_dir": str(CLIP_DIR),
                "trials": trials,
                "spec": {
                    "experiment": "0064",
                    "arms": list(ARMS),
                    "decoder": "finetuned (0063 adversarial best.pt), both arms",
                    "v3_seeds": [c["seed"] for c in v3],
                    "v2_seeds": [c["seed"] for c in v2],
                    "real_bouts": [c["bout"] for c in reals],
                },
            }
            pool_json = OUT / "pool.json"
            pool_json.write_text(json.dumps(payload, indent=2))
            result = subprocess.run(
                [str(REPO / "fieldserver" / ".venv" / "bin" / "python"),
                 str(REPO / "fieldserver" / "tools" / "register_pool.py"),
                 str(pool_json), "--dose-size", str(DOSE),
                 "--cooldown", str(COOLDOWN_MIN)],
                capture_output=True, text=True)
            stage.say(result.stdout.strip() or result.stderr.strip())
            if result.returncode != 0:
                raise RuntimeError(f"register_pool: {result.stderr.strip()}")
            run.note(result.stdout.strip())
        run.note(f"pool {POOL_NAME}: {len(trials)} trials in {len(BLOCK_PLAN)} "
                 f"blocks, dose {DOSE}, cooldown {COOLDOWN_MIN} min — on the "
                 "dashboard Listening panel")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print("registered", POOL_NAME)


if __name__ == "__main__":
    main()
