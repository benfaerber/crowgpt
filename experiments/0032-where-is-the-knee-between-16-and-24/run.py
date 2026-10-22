"""Is there a perceptual knee between 16 and 24 codebooks, blind?

0028 asked where the codec stops being audible and built its blinded sitting as
raw / K=8 / K=16, because PLAN-TIMBRE's branch structure assumed K* would be 16
or below. The sitting came back with raw 0.85, K=16 0.65, K=8 0.45 — the K=8 gap
resolved, the two 20-point steps not.

Then Ben browsed the LABELLED ladder and said something the blinded page could
not have caught, because it never played those rungs:

    "K=8 major robot vibes. K=16 is similar to K=8. K=24 is pretty good.
     K=32 less but still a little. K=32 is the superior one."

If that survives blinding it moves the whole question. It would mean the
threshold sits between 16 and 24 rather than below 16, that K=16 buys nothing
audible over K=8 — consistent with the blinded sitting, where their gap was not
resolved — and that even the maximum rung is not fully clean, which is what
0028's plateau already suggested.

WHY IT MIGHT NOT SURVIVE. It was read off a labelled page, in the direction the
labels invite. And neither automated instrument shows a knee there: STFT runs
1.077 -> 1.046 across 16 -> 24 and AST FAD 32.9 -> 30.8, both smooth, both
already flattening. Something also has to be explained if it IS true — in an RVQ
each successive stage carries a smaller residual, so stages 16-23 mattering while
8-15 do not is not the shape the codec's construction predicts.

THE DESIGN, AND WHY IT IS BIGGER THAN THE LAST ONE. Four arms — raw, K=16, K=24,
K=32 — at 30 disjoint bouts each, 120 trials. K=16 is in as the anchor the last
sitting already placed, so the two sittings can be lined up; K=8 is out because
0028 resolved it. Thirty an arm rather than twenty because 0028's failure mode
was power: at 20 it could only settle the 40-point gap, and the differences being
chased here may be 20-30. Thirty resolves about 25 points. It still cannot settle
a 10-point equivalence, and nothing here should be read as proving transparency.

Ben rated the last sitting at 3.3 s a clip, so 120 trials is about seven minutes.
That is the only reason this size is affordable.

Bouts are disjoint from every bout used in 0028, so nothing is heard twice across
the two sittings.
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
import torch

from crowgpt.codec import Codec, normalise
from crowgpt.demo import RatingPage
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
PAGE = HERE / "results" / "rate-upper-rungs-blind.html"

SPECIES = "american-crow"
ARMS = (("raw", None), ("k16", 16), ("k24", 24), ("k32", 32))
PER_ARM = 30
# 0028 consumed the first 260 held-out recordings: 200 for its automated ladder
# and 60 for its blinded sitting. Start past them so no bout is heard twice
# across the two sittings, which would let recognition stand in for quality.
SKIP = 260


def main():
    run = Run("0032 — THE KNEE BETWEEN 16 AND 24",
              ["choose", "decode", "page"])
    try:
        store = BoutStore(DATA / "bouts")
        with run.stage("choose") as stage:
            splits = store.split(seed=0)
            held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
            seen, chosen = set(), []
            for i in held:
                recording = store.index[i]["recording_id"]
                if recording in seen:
                    continue
                seen.add(recording)
                chosen.append(i)
                if len(chosen) >= SKIP + PER_ARM * len(ARMS):
                    break
            pool = chosen[SKIP:]
            if len(pool) < PER_ARM * len(ARMS):
                raise SystemExit(
                    f"only {len(pool)} unused recordings past 0028's {SKIP}, "
                    f"need {PER_ARM * len(ARMS)} — lower PER_ARM rather than reusing bouts"
                )
            stage.say(f"{len(pool)} unused recordings, {PER_ARM} per arm")

        codec = Codec(bandwidth=24.0)
        clips, cursor = [], 0
        with run.stage("decode") as stage:
            for arm, keep in ARMS:
                for n, position in enumerate(pool[cursor:cursor + PER_ARM]):
                    samples = normalise(store.audio(store.index[position]))
                    if keep is None:
                        audio = samples
                    else:
                        codes = codec.encode(samples).numpy()[0]
                        audio = codec.decode(torch.from_numpy(codes[:keep]))[0]
                    clips.append({
                        "audio": audio, "sr": 24000, "arm": arm,
                        "bout": int(position),
                        "recording": store.index[position]["recording_id"],
                    })
                    stage.update(len(clips), PER_ARM * len(ARMS), extra=arm)
                cursor += PER_ARM

        with run.stage("page") as stage:
            RatingPage(clips, {
                "Question": "is there a knee between 16 and 24 codebooks",
                "Arms": f"raw / K=16 / K=24 / K=32, {PER_ARM} disjoint bouts each",
                "Model involved": "none — every clip is a real recording",
                "Power": "resolves a ~25-point difference; not an equivalence test",
                "Bouts": f"disjoint from 0028's, so nothing is heard twice",
            }, seed=0).write(PAGE)
            stage.say(str(PAGE))

        (OUT / "clips.json").write_text(json.dumps(
            [{k: v for k, v in c.items() if k != "audio"} for c in clips], indent=2))
        run.note(f"{len(clips)} trials across {len(ARMS)} arms -> {PAGE}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print("wrote", PAGE)


if __name__ == "__main__":
    main()
