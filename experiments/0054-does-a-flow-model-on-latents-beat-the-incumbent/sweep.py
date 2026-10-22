"""Where along the path should the training signal go? Sweep the logit-normal mean.

WHY THIS AND NOT SOMETHING ELSE. 0054's partial-noise diagnostic localised the
failure precisely: from t=0.3 the model reconstructs to 100% detection, from t=0.0
it manages 41.7%. Everything is lost in the noise-dominated stretch where global
structure has to be invented. Moving the training signal there with a logit-normal
timestep took detection 25.0% -> 52.8%, and the gain landed exactly where the
signal moved. But **-0.5 was a first guess and was never tuned**, and t=0.0 is
still where the model fails.

SHORT RUNS, ONE VARIABLE. Every arm is 12,000 steps rather than 30,000 — enough
to rank, a third of the cost, and the incumbent arm at -0.5 is re-trained at 12k
too so the comparison is like-for-like rather than against the 30k number. The
winner is then trained fully. This is the standard design and its standard risk
is that a ranking at 12k need not hold at 30k; the full run is what settles it.

BIRDNET IS THE SCORER HERE AND THAT IS A COMPROMISE WORTH NAMING. 0022 recorded
that BirdNET selected this corpus, so tuning against it risks optimising for
"agrees with the thing that chose the training data" rather than for sounding
like a crow — the incumbent scoring mean confidence 0.8601 against real audio's
0.7486 is what that looks like at the limit. Three things make it tolerable and
none of them make it a verdict:

  - the marginal control scores 0.0%, so the axis is not measuring nothing
  - the ceiling arm scores 91.7%, so the axis has room and a known top
  - churn, the alternative, was flat (+0.0188 -> +0.0182) across a change that
    doubled detection, i.e. blind to exactly this

So the output is a SHORTLIST THAT HAS EARNED A SITTING, in 0047's words about
churn, and never a change anyone should believe without an ear.
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

from crowgpt.progress import Run

OUT = Path(__file__).resolve().parent
DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
LATENTS = DATA / "latents"
PYTHON = HERE / ".venv" / "bin" / "python"
STEPS = 12000
PER_ARM = 36

# sigmoid(mean) is the median timestep, i.e. where the training mass sits.
#   0.0 -> 0.500   -0.5 -> 0.378   -1.0 -> 0.269   -1.5 -> 0.182   -2.0 -> 0.119
MEANS = (0.0, -0.5, -1.0, -1.5, -2.0)


def train(mean, out_dir):
    subprocess.run(
        [str(PYTHON), "-m", "crowgpt.cli", "flow-train",
         "--steps", str(STEPS), "--eval-every", "1000",
         "--t-sampling", "logit_normal", "--t-mean", str(mean),
         "--out", str(out_dir)],
        cwd=str(HERE), check=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def score(out_dir, judge, ambience, sampler_cache):
    """Detection rate for one checkpoint, on the same ambience as every other."""
    from crowgpt.flow_sample import FlowSampler

    sampler = FlowSampler(out_dir, LATENTS)
    clips = sampler.generate(count=PER_ARM, steps=32, seed=54)
    scored = [c if c is not None else 0.0
              for c in judge.confidences([ambience.place(c) for c in clips])]
    values = np.array(scored)
    del sampler
    import torch

    torch.cuda.empty_cache()
    return float((values >= judge.crow_min).mean()), float(values.mean())


def main():
    from crowgpt.corpus import Corpus
    from crowgpt.judge import Ambience, BirdNetJudge

    run = Run("0054 — TIMESTEP SWEEP", ["train", "score", "report"])
    try:
        recordings = [r for recs in Corpus().recordings().values() for r in recs[:6]]
        if not recordings or isinstance(recordings[0], str):
            raise SystemExit("no ambience recordings — every arm would be judged in silence")
        ambience = Ambience(recordings, wanted=24, seed=0)
        judge = BirdNetJudge()

        directories = {}
        with run.stage("train") as stage:
            for i, mean in enumerate(MEANS):
                out_dir = HERE / "results" / f"sweep-t{mean:+.1f}".replace(".", "p")
                directories[mean] = out_dir
                if not (out_dir / "model.pt").exists():
                    train(mean, out_dir)
                stage.update(i + 1, len(MEANS), extra=f"mean {mean:+.1f}")

        results = {}
        with run.stage("score") as stage:
            for i, mean in enumerate(MEANS):
                detected, confidence = score(directories[mean], judge, ambience, None)
                results[f"{mean:+.1f}"] = {"mean": mean, "detected": round(detected, 4),
                                           "mean_conf": round(confidence, 4),
                                           "median_t": round(1 / (1 + np.exp(-mean)), 3)}
                stage.update(i + 1, len(MEANS), extra=f"{mean:+.1f} {detected:.1%}")

        with run.stage("report") as stage:
            print(f"\n{'t_mean':>8s} {'median t':>9s} {'detected':>10s} {'mean conf':>10s}")
            for key, row in results.items():
                print(f"{key:>8s} {row['median_t']:9.3f} {row['detected']:10.1%} "
                      f"{row['mean_conf']:10.4f}")
            best = max(results.values(), key=lambda r: r["detected"])
            print(f"\nbest t_mean {best['mean']:+.1f} at {best['detected']:.1%} "
                  f"({STEPS} steps, n={PER_ARM}, +/-16 points)")
            print("A shortlist that has earned a sitting, never a verdict — "
                  "BirdNET selected this corpus (0022).")
            payload = {"steps": STEPS, "per_arm": PER_ARM, "arms": results,
                       "best_mean": best["mean"],
                       "note": "12k-step ranking; a full run settles it. BirdNET is "
                               "circular (0022) and churn was blind to the change "
                               "that doubled detection, so this is triage."}
            (OUT / "sweep.json").write_text(json.dumps(payload, indent=2) + "\n")
            stage.say(f"best {best['mean']:+.1f} at {best['detected']:.1%}")
        run.note(f"best t_mean {best['mean']:+.1f} · {best['detected']:.1%}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
