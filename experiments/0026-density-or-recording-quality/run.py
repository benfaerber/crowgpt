"""Is it the density, or is it just that the short clips are bad recordings?

0025 found a real but modest effect — good-rate rose 62% -> 75% -> 88% -> 100%
across 0, 1, 2 and 3+ units, Spearman p=0.046 — and Ben immediately named the
confound himself: "the archive has a lot of low quality single bout recordings
that are short and choppy sounding." If poor recordings yield both fewer clean
bursts AND a worse sound, density and quality are tangled and 0025 cannot say
which is doing the work.

The archive's own A-E ratings cannot settle it: only 2% of the corpus joins to
one, and those are 245 A's against 5 C's and a single D. There is nothing to
stratify.

SO HOLD THE RECORDING CONSTANT INSTEAD. For each of 14 recordings, take two
bouts from THE SAME FILE — one with a single unit, one with three or more,
durations matched within 0.6 s. Same microphone, same bird, same distance, same
noise floor, same recordist, same day. Duration matched so length cannot stand
in for density. The only thing that differs is how many caws are in it.

  if the 1-unit clip rates worse than its own partner  -> density is causal
  if the pair rates the same                            -> 0025 measured the
                                                           recordings, not the
                                                           density

TWO GENERATED ARMS, split on the same axis, because 0025's most interesting
number was that generated clips with 2+ units rated 5/5 good while those with
1 or 0 rated 0/3. Those are five and three clips. This puts ten behind each.

SNR IS RECORDED PER CLIP as a covariate rather than a filter — energy inside the
detected units against energy outside, in dB. If ratings track SNR better than
they track unit count, Ben's confound wins on the evidence rather than by
assertion, and it will be visible in the same session.

UNSURE IS AN OPTION NOW. Ben is calibrated on caws and says so: "the rattle /
chatter is a softsong so im not quite as used to it". Forcing a binary there
manufactures data where he has none.
"""
import json
import sys
from collections import defaultdict
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
PAGE = HERE / "results" / "rate-density.html"
OUT = Path(__file__).resolve().parent

PAIRS = 14
PER_GEN = 10
MATCH_SEC = 0.6
SPECIES = "american-crow"


def measure(audio, units):
    """Duty cycle and a crude in-band SNR, so quality is a covariate not a guess."""
    seconds = audio.size / SAMPLE_RATE
    inside = np.zeros(audio.size, dtype=bool)
    for start, end in units:
        inside[int(start * SAMPLE_RATE):int(end * SAMPLE_RATE)] = True
    signal = audio[inside]
    noise = audio[~inside]
    if signal.size and noise.size:
        snr = 20 * np.log10((np.sqrt((signal ** 2).mean()) + 1e-9) /
                            (np.sqrt((noise ** 2).mean()) + 1e-9))
    else:
        snr = float("nan")
    return {
        "seconds": round(seconds, 2),
        "duty": round(float(inside.mean()), 3),
        "snr_db": None if np.isnan(snr) else round(float(snr), 1),
    }


def main():
    run = Run("0026 — DENSITY OR RECORDING QUALITY",
              ["pair up", "generate", "page"])
    clips = []
    try:
        segmenter = Segmenter()
        store = BoutStore(DATA / "bouts")
        splits = store.split(seed=0)

        with run.stage("pair up") as stage:
            held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
            by_recording = defaultdict(list)
            for position in held:
                row = store.index[position]
                audio = normalise(store.audio(row))
                if audio.size / SAMPLE_RATE < 1.2:
                    continue
                _, units = segmenter.segment(audio, SAMPLE_RATE)
                by_recording[row["recording_id"]].append((position, audio, units))

            made = 0
            for recording, items in by_recording.items():
                if made >= PAIRS:
                    break
                singles = [x for x in items if len(x[2]) == 1]
                multis = [x for x in items if len(x[2]) >= 3]
                pair = next((
                    (s, m) for s in singles for m in multis
                    if abs(s[1].size - m[1].size) / SAMPLE_RATE <= MATCH_SEC), None)
                if pair is None:
                    continue
                made += 1
                for kind, (position, audio, units) in (("single", pair[0]), ("multi", pair[1])):
                    clips.append({"audio": audio, "source": "real", "arm": kind,
                                  "units": len(units), "pair": made,
                                  "recording": recording, "clip_id": len(clips),
                                  **measure(audio, units)})
                stage.update(made, PAIRS)
            stage.say(f"{made} within-recording pairs")

        with run.stage("generate") as stage:
            from crowgpt.sample import Sampler
            sampler = Sampler(MODEL, token_dir=TOKENS)
            want = {"single": PER_GEN, "multi": PER_GEN}
            got = {"single": 0, "multi": 0}
            seed = 11000
            while sum(got.values()) < sum(want.values()) and seed < 11000 + 600:
                audio = sampler.audio(SPECIES, seed=seed)
                seed += 1
                if audio.size / SAMPLE_RATE < 1.2:
                    continue
                _, units = segmenter.segment(audio, SAMPLE_RATE)
                arm = "single" if len(units) <= 1 else ("multi" if len(units) >= 3 else None)
                if arm is None or got[arm] >= want[arm]:
                    continue
                got[arm] += 1
                clips.append({"audio": audio, "source": "generated", "arm": arm,
                              "units": len(units), "pair": None,
                              "recording": None, "clip_id": len(clips),
                              **measure(audio, units)})
                stage.update(sum(got.values()), sum(want.values()))
            stage.say(f"generated single {got['single']}, multi {got['multi']}")

        with run.stage("page") as stage:
            RatingPage(clips, {
                "Clips": len(clips),
                "Design": "same recording, 1 unit vs 3+ units",
                "Duration": "matched within 0.6 s",
                "Waveform": "hidden until rated",
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
