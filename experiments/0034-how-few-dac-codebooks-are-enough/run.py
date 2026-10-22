"""How few DAC-24 codebooks are enough?

0033 found the tokenizer: DAC 24 kHz at 32 codebooks is the only arm a listener
cannot separate from raw, and it beats EnCodec at 32 codebooks by 27 points on
identical sequence length. But 32 codebooks is 7,200 tokens for a 3-second bout,
and 0030 showed a flat model at 3,619 tokens already fails to beat one at 1,811.
So the tokenizer question is answered and the sequence-length question is not.

ONLY 32 HAS BEEN HEARD. 0017 tested DAC-24 at 8 and 12 codebooks and found both
poor, but on BirdNET retention — the instrument that ranked DAC last overall
while the ear ranks it first, and which has now produced the wrong call twice.
The rungs between, 16 through 24, have never been played to anyone.

WHAT TURNS ON IT. DAC-24 at 16 codebooks is 3,600 tokens and at 12 it is 2,700.
The current generator handles 1,811. Every codebook that can be dropped without
a listener noticing is sequence length the model does not have to learn, and the
difference between "transparency costs 7,200 tokens" and "transparency costs
2,700" decides whether WP2's extender is necessary or whether a flat model is
viable again.

FIVE ARMS: raw, and DAC-24 at 12, 16, 24, 32. The 32 rung repeats 0033's winner
as the within-sitting anchor, so this sitting does not have to be compared
across to anything — which matters, because 0033's raw anchor moved and its
cross-sitting comparisons had to be thrown out.

24 bouts an arm rather than 30, because five arms at 30 is 150 trials and the
last four sittings have run 3.3 s a clip; 120 is the size that has worked. This
resolves roughly a 28-point difference, which is enough to find a knee and not
enough to prove transparency at any rung.

Same protections as 0033: bouts at least a second long, every clip peak
normalised after decoding, and nothing reused from 0028, 0032 or 0033.
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

from crowgpt.codec import normalise
from crowgpt.dac_codec import DacCodec
from crowgpt.demo import RatingPage
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
PAGE = HERE / "results" / "rate-dac24-ladder-blind.html"

SPECIES = "american-crow"
PER_ARM = 24
MIN_SECONDS = 1.0
# 0028 took the first 260 one-per-recording bouts, 0032 the next 120, and 0033
# drew 120 more from the >=1s bouts past 380. Start clear of all of them.
SKIP = 380
DROPPED_BY_0033 = 120
RUNGS = (None, 12, 16, 24, 32)   # None is the raw arm
SR = 24000


def main():
    run = Run("0034 — HOW FEW DAC CODEBOOKS",
              ["choose", "decode", "page"])
    try:
        store = BoutStore(DATA / "bouts")
        with run.stage("choose") as stage:
            splits = store.split(seed=0)
            held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
            seen, ordered = set(), []
            for i in held:
                recording = store.index[i]["recording_id"]
                if recording in seen:
                    continue
                seen.add(recording)
                ordered.append(i)
            # Same construction 0033 used, then skip exactly what it consumed.
            long_enough = [i for i in ordered[SKIP:]
                           if store.index[i]["n_samples"] / SR >= MIN_SECONDS]
            pool = long_enough[DROPPED_BY_0033:]
            need = PER_ARM * len(RUNGS)
            if len(pool) < need:
                raise SystemExit(
                    f"only {len(pool)} unused bouts over {MIN_SECONDS}s remain; need {need}. "
                    f"Lower PER_ARM rather than reusing bouts."
                )
            pool = pool[:need]
            stage.say(f"{len(pool)} bouts, {PER_ARM} per arm, none used in 0028/0032/0033")

        clips = []
        with run.stage("decode") as stage:
            cursor = 0
            for rung in RUNGS:
                arm = "raw" if rung is None else f"dac24_{rung}"
                picks = pool[cursor:cursor + PER_ARM]
                cursor += PER_ARM
                dac = None if rung is None else DacCodec(n_codebooks=rung, model_type="24khz")
                for position in picks:
                    samples = normalise(store.audio(store.index[position]))
                    audio = samples if dac is None else dac.roundtrip(samples)[0]
                    clips.append({
                        "audio": normalise(np.asarray(audio, dtype=np.float32)),
                        "sr": SR, "arm": arm, "bout": int(position),
                        "recording": store.index[position]["recording_id"],
                        "tokens_per_3s": None if rung is None else rung * 225,
                        "seconds": round(store.index[position]["n_samples"] / SR, 2),
                    })
                    stage.update(len(clips), need, extra=arm)
                if dac is not None:
                    del dac
                    torch.cuda.empty_cache()

        with run.stage("page") as stage:
            RatingPage(clips, {
                "Question": "how few DAC-24 codebooks before a listener notices",
                "Arms": f"raw / DAC-24 at 12, 16, 24, 32 codebooks, {PER_ARM} bouts each",
                "Tokens per 3 s": "12cb 2,700 · 16cb 3,600 · 24cb 5,400 · 32cb 7,200",
                "Model involved": "none — every clip is a real recording",
                "Levels": "every clip peak-normalised after decoding, raw included",
                "Power": "resolves a ~28-point difference; not an equivalence test",
            }, seed=0).write(PAGE)
            stage.say(str(PAGE))

        (OUT / "clips.json").write_text(json.dumps(
            [{k: v for k, v in c.items() if k != "audio"} for c in clips], indent=2))
        run.note(f"{len(clips)} trials across {len(RUNGS)} arms -> {PAGE}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print("wrote", PAGE)


if __name__ == "__main__":
    main()
