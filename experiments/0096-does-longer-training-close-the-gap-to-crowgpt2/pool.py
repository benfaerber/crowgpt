"""0096, the sitting: the 60k candidate against CrowGPT2, by ear.

0086's instrument (its sampler settings, its real-anchor selection, its
clip features), with two changes: the candidate is 0096's best snapshot,
and six comparisons come back a second time with the sides swapped, so the
ear's own repeatability is measured for the first time (0095's caveat).
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "experiments/0086-can-tuned-training-improve-crowgpt2"))

import numpy as np
import soundfile as sf

import finish
from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore
from crowgpt.train import require_device
from training import atomic_json

POOL_NAME = "capacity-0096"
finish.POOL_NAME = POOL_NAME
OUTPUT = REPO / "crowgpt/results/longer-0096"
CLIP_DIR = REPO / "crowgpt/results/listening-pools" / POOL_NAME
MODELS = {"crowgpt2": finish.INCUMBENT,
          "candidate": OUTPUT / "60k-lr-6e-4/step-60000.pt"}
GATE_SEED, POOL_SEED = 86000, 96000
BLOCKS = [(14, 4, 0), (13, 2, 3), (13, 2, 3)]


class Schedule:
    """54 trials in three doses of 18: 40 comparisons, 8 catches, 6 repeats."""

    def __init__(self, arms, anchors, catch_reals, seed=96):
        self.arms, self.anchors, self.catch_reals = arms, anchors, catch_reals
        self.rng = np.random.default_rng(seed)

    @staticmethod
    def balanced(n, rng):
        sides = [True, False] * (n // 2 + 1)
        sides = sides[:n]
        rng.shuffle(sides)
        return sides

    def compare(self, i, candidate_first):
        a, b = ("candidate", "crowgpt2") if candidate_first else ("crowgpt2", "candidate")
        first, second = self.arms[a]["rows"][i], self.arms[b]["rows"][i]
        return {"kind": "compare", "first_clip": first["file"], "second_clip": second["file"],
                "first_arm": a, "second_arm": b,
                "facts": {a: {"seed": first["seed"], "seconds": first["seconds"]},
                          b: {"seed": second["seed"], "seconds": second["seconds"]}}}

    def catch(self, n, arm, i, real_first):
        generated = self.arms[arm]["rows"][i]
        real = {"file": self.catch_reals[n]}
        first, second, a, b = (real, generated, "real", arm) if real_first else (generated, real, arm, "real")
        return {"kind": "catch", "first_clip": first["file"], "second_clip": second["file"],
                "first_arm": a, "second_arm": b, "facts": {"generated_seed": generated["seed"]}}

    def trials(self):
        rng = self.rng
        compares = list(range(40))
        rng.shuffle(compares)
        catches = [("candidate", i) for i in range(40, 44)] + [("crowgpt2", i) for i in range(40, 44)]
        rng.shuffle(catches)
        out, shown, ci, ki = [], [], 0, 0
        for block, (n_compare, n_catch, n_repeat) in enumerate(BLOCKS):
            slots = ["compare"] * n_compare + ["catch"] * n_catch + ["repeat"] * n_repeat
            rng.shuffle(slots)
            compare_sides = self.balanced(n_compare, rng)
            catch_sides = self.balanced(n_catch, rng)
            earlier = [t for t in shown if t["block"] < block and "repeated" not in t]
            again = list(rng.choice(len(earlier), n_repeat, replace=False)) if n_repeat else []
            for kind in slots:
                if kind == "compare":
                    trial = self.compare(compares[ci], compare_sides.pop())
                    trial["anchor_clip"] = self.anchors[ci + ki]
                    trial["facts"]["pair"] = compares[ci]
                    ci += 1
                elif kind == "catch":
                    arm, i = catches[ki]
                    trial = self.catch(ki, arm, i, catch_sides.pop())
                    trial["anchor_clip"] = self.anchors[ci + ki]
                    ki += 1
                else:
                    original = earlier[again.pop()]
                    original["repeated"] = True
                    pair = original["facts"]["pair"]
                    trial = self.compare(pair, original["first_arm"] != "candidate")
                    trial["kind"] = "repeat"
                    trial["anchor_clip"] = original["anchor_clip"]
                    trial["facts"]["pair"] = pair
                trial["block"] = block
                out.append(trial)
                if kind == "compare":
                    shown.append(trial)
        for trial in out:
            trial.pop("repeated", None)
        return out


class Sitting:
    def __init__(self):
        self.store = BoutStore(finish.DATA / "crowgpt/bouts-6s")
        self.run = Run("0096 listening pool", ["gate candidate", "pool crowgpt2",
                                               "pool candidate", "register"])

    def gate(self):
        with self.run.stage("gate candidate") as stage:
            sampler = Sampler(MODELS["candidate"], decoder_state="finetuned", device="cuda")
            drawn = finish.draw(sampler, stage, GATE_SEED, 100)
            del sampler
            finish.cleanup()
        previous = json.loads((REPO / "crowgpt/results/tuning-0086/gate.json").read_text())
        summaries = {"real": previous["real"]["summary"], "crowgpt2": previous["crowgpt2"]["summary"],
                     "0086 selected": previous["candidate"]["summary"], "candidate": drawn["summary"]}
        atomic_json(OUTPUT / "gate.json", {"candidate": drawn, "summaries": summaries})
        return summaries

    def draws(self):
        arms = {}
        CLIP_DIR.mkdir(parents=True, exist_ok=True)
        for arm, path in MODELS.items():
            with self.run.stage(f"pool {arm}") as stage:
                sampler = Sampler(path, decoder_state="finetuned", device="cuda")
                arms[arm] = finish.draw(sampler, stage, POOL_SEED, 44, CLIP_DIR, arm)
                del sampler
                finish.cleanup()
        return arms

    def reals(self):
        chosen = finish.select_reals(self.store)
        anchors, catch_reals = [], []
        for n, i in enumerate(chosen):
            filename = f"real-{n:02d}.wav"
            sf.write(CLIP_DIR / filename, normalise(self.store.audio(self.store.index[i])),
                     SAMPLE_RATE, subtype="PCM_16")
            (anchors if n < 48 else catch_reals).append(filename)
        return chosen, anchors, catch_reals

    def register(self, arms, summaries):
        with self.run.stage("register") as stage:
            chosen, anchors, catch_reals = self.reals()
            trials = Schedule(arms, anchors, catch_reals).trials()
            payload = {"name": POOL_NAME, "question": finish.QUESTION, "clip_dir": str(CLIP_DIR),
                       "dose_size": 18, "reveal_at": len(trials), "trials": trials,
                       "spec": {"experiment": "0096", "sampling": finish.SAMPLING,
                                "decoder": "finetuned", "candidate": str(MODELS["candidate"].relative_to(REPO)),
                                "repeats": 6, "draws": arms, "anchor_bouts": chosen,
                                "anchor_groups": [self.store.index[i]["group_key"] for i in chosen]}}
            atomic_json(OUTPUT / "pool.json", payload)
            done = subprocess.run([str(REPO / "fieldserver/.venv/bin/python"),
                                   str(REPO / "fieldserver/tools/register_pool.py"),
                                   str(OUTPUT / "pool.json"), "--dose-size", "18", "--cooldown", "30"],
                                  text=True, capture_output=True)
            if done.returncode:
                raise RuntimeError(done.stdout + done.stderr)
            self.run.note(done.stdout.strip())
            atomic_json(HERE / "pool_results.json", {"pool": POOL_NAME, "trials": len(trials),
                                                      "gate": summaries})
            stage.update(1, 1, extra=f"{len(trials)} trials registered")
            print(done.stdout.strip())
            print(json.dumps(summaries, indent=1))


def main():
    if POOL_NAME in dict(finish.pool_specs()):
        print(f"Pool {POOL_NAME} already exists; leaving it untouched")
        return
    if require_device() != "cuda":
        raise RuntimeError("GPU required")
    sitting = Sitting()
    summaries = sitting.gate()
    sitting.register(sitting.draws(), summaries)


if __name__ == "__main__":
    main()
