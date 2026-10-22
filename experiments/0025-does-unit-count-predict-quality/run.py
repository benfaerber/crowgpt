"""Is "sounds good" just "has more than one caw in it"?

On ten bouts from one recording, Ben's good/bad split matched the burst count
exactly: every clip he called bad held ONE unit, every one he called good held
two to four. He described the good ones as having "peaks and valleys" in the
waveform, which is what a bout with gaps between caws looks like, and the bad
ones as choppy clicking — which is what one continuous blob of energy at 70-96%
duty cycle sounds like.

If that holds on a proper sample it reorganises most of what this project
believes about its own output. 0024 found the generator makes single-unit clips
70% of the time against real audio's 33%, and that was read as a tell. If unit
count is instead the QUALITY axis, then "generated sounds worse" and "generated
is mostly single-unit" are one fact rather than two, and the defect starts in
segmentation rather than in the model.

FOUR STRATA, one question each.

  real, 1 unit      does real audio sound bad when it holds a single burst?
  real, 2 units     the hypothesis says these start sounding right
  real, 3+ units    and these should be the good ones
  generated, 1 unit at matched unit count, is there a penalty for being generated?

The last stratum is what separates the two explanations. If generated one-unit
clips rate the same as real one-unit clips, unit count explains the whole thing
and the model adds nothing bad. If they rate worse, the model has a defect
beyond density.

ONE BOUT PER RECORDING. Bouts are consecutive slices of one file, so taking
neighbours samples a recording rather than the corpus — the mistake that made
the first codec page unreadable.

THE WAVEFORM IS HIDDEN by RatingPage until each clip is rated. Ben can see
choppiness in the picture, so a page that draws it would be asking him to count
peaks instead of listening.
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

from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import RatingPage
from crowgpt.progress import Run
from crowgpt.segment import Segmenter
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
MODEL = HERE / "results" / "sweep-0023" / "batch-32-dropout-0" / "model.pt"
TOKENS = DATA / "tokens-calltype"
PAGE = HERE / "results" / "rate-units.html"
OUT = Path(__file__).resolve().parent
PER_STRATUM = 8
SPECIES = "american-crow"


def duty(units, seconds):
    return round(sum(e - s for s, e in units) / seconds, 3) if seconds else 0.0


def main():
    run = Run("0025 — DOES UNIT COUNT PREDICT QUALITY",
              ["real strata", "generated", "page"])
    clips = []
    try:
        segmenter = Segmenter()
        store = BoutStore(DATA / "bouts")
        splits = store.split(seed=0)

        with run.stage("real strata") as stage:
            held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
            # ZERO IS ITS OWN STRATUM, and the first version of this buried it.
            # Bucketing len(units) <= 1 together put six 0-unit clips in a bucket
            # labelled "1", which is not one caw — it is a bout the detector
            # found no burst in at all. Those are a different thing and possibly
            # the worst thing, so they get measured rather than blended.
            want = {"0": PER_STRATUM, "1": PER_STRATUM, "2": PER_STRATUM, "3+": PER_STRATUM}
            got, seen = {k: 0 for k in want}, set()
            for position in held:
                if all(got[k] >= want[k] for k in want):
                    break
                recording = store.index[position]["recording_id"]
                if recording in seen:
                    continue
                samples = normalise(store.audio(store.index[position]))
                seconds = samples.size / SAMPLE_RATE
                if seconds < 0.8:
                    continue
                _, units = segmenter.segment(samples, SAMPLE_RATE)
                bucket = str(len(units)) if len(units) <= 2 else "3+"
                if got[bucket] >= want[bucket]:
                    continue
                seen.add(recording)
                got[bucket] += 1
                clips.append({"audio": samples, "source": "real", "units": len(units),
                              "bucket": bucket, "seconds": round(seconds, 2),
                              "duty": duty(units, seconds), "clip_id": len(clips)})
                stage.update(sum(got.values()), sum(want.values()))
            stage.say(" ".join(f"{k}:{v}" for k, v in got.items()))

        with run.stage("generated") as stage:
            from crowgpt.sample import Sampler
            sampler = Sampler(MODEL, token_dir=TOKENS)
            # TAKEN AS THEY COME, not forced into a bucket. Filtering generated
            # clips to a unit count would hide what the model actually does, and
            # what it actually does is most of the question. Whatever counts
            # arrive get recorded and compared against the real strata after.
            made, seed = 0, 9000
            while made < PER_STRATUM and seed < 9000 + 200:
                audio = sampler.audio(SPECIES, seed=seed)
                seed += 1
                if audio.size < SAMPLE_RATE * 0.8:
                    continue
                seconds = audio.size / SAMPLE_RATE
                _, units = segmenter.segment(audio, SAMPLE_RATE)
                made += 1
                clips.append({"audio": audio, "source": "generated", "units": len(units),
                              "bucket": str(len(units)) if len(units) <= 2 else "3+",
                              "seconds": round(seconds, 2),
                              "duty": duty(units, seconds), "clip_id": len(clips)})
                stage.update(made, PER_STRATUM)
            stage.say(f"{made} generated, as they come")

        with run.stage("page") as stage:
            RatingPage(clips, {
                "Clips": len(clips),
                "Strata": "real 1 / 2 / 3+ units, generated 1 unit",
                "Waveform": "hidden until rated",
                "Species": "American Crow",
            }).write(PAGE)
            (OUT / "manifest.json").write_text(json.dumps(
                [{k: v for k, v in c.items() if k != "audio"} for c in clips], indent=2) + "\n")
            stage.say(str(PAGE))
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print("wrote", PAGE, "with", len(clips), "clips")


if __name__ == "__main__":
    main()
