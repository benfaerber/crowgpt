"""Crow plus modem: the generator holds coarse codes too long.

Ben, 2026-08-04, on hearing a generated bout next to a real one and a codec
round-trip of the same recording:

    "codec seems good, possibly minor quality degredation. ai gen it matches the
     shape of crow calls good. but it still does have some modem type sounds. so
     it is crow + modem"

TWO THINGS IN THAT, AND THE SECOND IS MEASURABLE. He localises the defect: the
codec is nearly fine and the modem arrives with the model. And "modem" is a
sharper word than "robotic" — a modem is periodic. Sustained, tonal, repeating.
That is a prediction about the token stream, not a feeling about it.

WHAT WOULD MAKE AUDIO SOUND PERIODIC. A codec frame is 13 ms. If the generator
holds the same codebook entry across neighbouring frames more often than real
audio does, the decoded waveform sustains the same spectral shape instead of
moving, and a sustained repeating shape is exactly what a modem is.

`stages.py` predicted this in a docstring, before anyone heard it:

    "Cooling a correctly-uncertain distribution does not clean it up; it makes
     the sampler re-pick the same arbitrary residual code over and over, which
     is periodic, and periodic is what 'robotic' sounds like."

THE MEASUREMENT is one line: the fraction of adjacent frame pairs where a
codebook's entry changes. Real audio sets the target; anything below it is a
generator that is too sticky. No listening, no labels, sixty bouts a side.

TOP-K IS THE FIRST SUSPECT because truncating to the 200 most likely ids removes
exactly the tail that would have broken a repeat, and 0043 already found it
flattening the output offline. 0044's 30-pair sitting could not resolve it by
ear (P(no top-k) = 0.41), which this run is not able to overturn — an offline
signal and a null by ear are the shape of 0023 and 0027 all over again, and the
ear wins. What this can say is whether the mechanism is real and how much of the
gap top-k owns.
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

from crowgpt.codec import Codec, normalise
from crowgpt.progress import Run
from crowgpt.sample import Sampler
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
SPECIES = "american-crow"
N = 60
MIN_FRAMES = 40
MODEL = HERE / "results" / "model-fair-k8"


def churn(grids):
    """Per stage, the fraction of adjacent frames whose code differs.

    1.0 means every frame picks a new entry; 0.0 means the code is held for the
    whole bout. Real audio is the only meaningful reference — there is no
    correct value in the abstract.
    """
    total, seen = np.zeros(8), 0
    for grid in grids:
        if grid.shape[1] < 2:
            continue
        total += (grid[:, 1:] != grid[:, :-1]).mean(axis=1)
        seen += 1
    return total / max(1, seen)


def main():
    run = Run("0046 — CROW PLUS MODEM", ["real", "generated", "report"])
    results = {}
    try:
        store = BoutStore(DATA / "bouts")
        with run.stage("real") as stage:
            splits = store.split(seed=0)
            held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
            seen, chosen = set(), []
            for i in held:
                recording = store.index[i]["recording_id"]
                if recording in seen:
                    continue
                seen.add(recording)
                chosen.append(i)
                if len(chosen) >= N:
                    break
            codec = Codec(bandwidth=6.0)
            grids = []
            for n, position in enumerate(chosen, 1):
                grids.append(codec.encode(
                    normalise(store.audio(store.index[position]))).numpy()[0])
                stage.update(n, len(chosen))
            results["real"] = churn(grids).tolist()
            stage.say(f"{len(grids)} bouts, one per recording")

        with run.stage("generated") as stage:
            sampler = Sampler(MODEL / "model.pt", token_dir=None)
            for label, top_k in (("top_k=200", 200), ("top_k=None", None)):
                grids, seed = [], 0
                while len(grids) < N and seed < N * 4:
                    grid = sampler.codec.unflatten(sampler.tokens(
                        SPECIES, temperature=1.0, top_k=top_k, seed=seed))
                    seed += 1
                    if grid.shape[1] >= MIN_FRAMES:
                        grids.append(grid)
                        stage.update(len(grids), N * 2, extra=label)
                results[label] = churn(grids).tolist()

        with run.stage("report") as stage:
            real = np.array(results["real"])
            lines = []
            for label in ("top_k=200", "top_k=None"):
                gap = np.array(results[label]) - real
                results[f"{label} gap"] = gap.tolist()
                lines.append(f"{label}: stage-0 {gap[0]:+.3f}, mean {gap.mean():+.3f}")
            (OUT / "results.json").write_text(json.dumps(results, indent=2))
            for line in lines:
                run.note("churn vs real — " + line)
            stage.say("wrote results.json")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
