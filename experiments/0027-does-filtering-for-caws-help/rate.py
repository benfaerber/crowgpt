"""Three arms, one sitting: real caws, the current model, the caw-filtered model.

0026 put real audio at 25/28 rated good and the current model at 6/24. This asks
whether training on confidently caw-like audio closes any of that.

EVERY MODEL IS ASKED FOR AN ALARM CALL rather than left to default. The filtered
model's American Crow data is alarm and call only, so conditioning it on
"unknown" would be out of distribution and would measure the prompt rather than
the corpus. 0021 measured the baseline responding to `alarm call` at 92.9%
recall, so the condition is well supported for both, and asking both the same
thing keeps the data as the only difference.

THE REAL ARM IS ALSO CAWS — held-out bouts the 0021 head confidently calls alarm
or call — so all three arms are the same kind of sound and the comparison is
about quality rather than about call type.

The criterion is printed on the page before the first clip this time. 0025 and
0026 disagreed by half on the generated arm because the standard was clarified
at clip twenty, and that is not a mistake worth making twice.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

from crowgpt.codec import SAMPLE_RATE, normalise
from crowgpt.demo import RatingPage
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
BASELINE = HERE / "results" / "sweep-0023" / "batch-32-dropout-0" / "model.pt"
FILTERED = HERE / "results" / "model-cawfiltered" / "model.pt"
BASE_TOKENS = DATA / "tokens-calltype"
FILT_TOKENS = DATA / "tokens-cawfiltered"
CONTROL = HERE / "results" / "model-randomcontrol" / "model.pt"
CTRL_TOKENS = DATA / "tokens-randomcontrol"
PAGE = HERE / "results" / "rate-cawfiltered.html"
OUT = Path(__file__).resolve().parent
PER_ARM = 12
SPECIES = "american-crow"
CAW = ("alarm call", "call")


def main():
    run = Run("0027 — RATE FOUR ARMS",
              ["real", "baseline", "filtered", "control", "page"])
    clips = []
    try:
        from crowgpt.sample import Sampler

        with run.stage("real") as stage:
            store = BoutStore(DATA / "bouts")
            splits = store.split(seed=0)
            types = {int(k): v for k, v in json.loads(
                (DATA / "bouts" / "call_types.json").read_text())["call_types"].items()}
            seen, made = set(), 0
            for position in splits["test"]:
                if made >= PER_ARM:
                    break
                row = store.index[position]
                if row["species"] != SPECIES or types.get(position) not in CAW:
                    continue
                if row["recording_id"] in seen:
                    continue
                audio = normalise(store.audio(row))
                if audio.size / SAMPLE_RATE < 1.0:
                    continue
                seen.add(row["recording_id"])
                made += 1
                clips.append({"audio": audio, "arm": "real", "clip_id": len(clips)})
                stage.update(made, PER_ARM)
            stage.say(f"{made} real caws, one per recording")

        # FOUR ARMS IN ONE SITTING. `control` is the same-size random subset, so
        # filtered-against-control isolates the filter from the 55% of the corpus
        # it removes — which 0027's first sitting could not do. All four are rated
        # together because 8.3 points of listener drift between sessions was
        # measured on identical weights on 2026-08-01, larger than the effect.
        for name, checkpoint, tokens in (("baseline", BASELINE, BASE_TOKENS),
                                         ("filtered", FILTERED, FILT_TOKENS),
                                         ("control", CONTROL, CTRL_TOKENS)):
            with run.stage(name) as stage:
                sampler = Sampler(checkpoint, token_dir=tokens)
                made, seed = 0, 21000
                while made < PER_ARM and seed < 21000 + 300:
                    audio = sampler.audio(SPECIES, call_type="alarm call", seed=seed)
                    seed += 1
                    if audio.size / SAMPLE_RATE < 1.0:
                        continue
                    made += 1
                    clips.append({"audio": audio, "arm": name, "clip_id": len(clips)})
                    stage.update(made, PER_ARM)
                stage.say(f"{made} clips")

        with run.stage("page") as stage:
            RatingPage(clips, {
                "Arms": "four, unnamed until rated",
                "Prompt": "alarm call, every model",
                "Clips": len(clips),
                # NOT the prior result. An earlier build printed "real 100%,
                # model 40%" here, which tells the rater what to expect before
                # he hears anything — a prime, on a page whose entire purpose is
                # an unprimed judgement.
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
