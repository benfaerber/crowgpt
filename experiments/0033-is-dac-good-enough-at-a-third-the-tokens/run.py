"""Is DAC clean enough at a third of EnCodec's tokens?

0017 rejected DAC, and it was right about the question it asked. That question
was retention AT MATCHED TOKEN COUNT: 1,813 DAC tokens against 1,800 EnCodec
tokens, where DAC kept 48% of BirdNET's detections and EnCodec 97%. The
constraint doing the work there was "the model's job must not get harder", and
under it DAC loses badly.

0032 removed that constraint. Blind, the only rung a listener cannot separate
from raw is EnCodec at 32 codebooks — 7,200 tokens for a 3-second bout. Every
cheaper rung is audibly worse. So the sequence length that buys transparency is
no longer 1,800; it is 7,200, and the interesting comparison is no longer at
matched tokens. It is:

    can anything reach raw-like quality for FEWER than 7,200 tokens?

DAC's 44 kHz model runs 86 frames a second with 9 codebooks, so a 3-second bout
is about 2,325 tokens — roughly a third of EnCodec-32, and 0017 measured its
spectral distance at 1.013 against EnCodec-32's 1.035. If it holds up by ear,
the sequence-length problem this project has had since 0018 dissolves: 2,325
tokens is close enough to the 1,811 the current generator already handles that a
flat model becomes viable again, and WP2's extender stops being necessary.

FOUR ARMS.

    raw            the ceiling, and the drift anchor across every sitting so far
    encodec-32     7,200 tokens — 0032's answer, the thing to beat
    dac44-9        2,325 tokens — DAC 44 kHz at full bandwidth, the candidate
    dac24-32       7,200 tokens — DAC 24 kHz at full bandwidth, matched tokens
                   to EnCodec-32, which separates "DAC is better" from "the
                   44 kHz frame rate is what buys it"

TWO TRAPS THIS AVOIDS, both found the hard way.

RESAMPLING. DacCodec.encode hands the model `self.sample_rate` and DAC's
preprocess trusts it, so feeding 24 kHz audio to the 44 kHz model does not
resample — it reinterprets, pitching the caw up and shortening it by 1.84x while
looking like it worked. The 44 kHz arm resamples in and back out, and the round
trip is transparent for a 24 kHz-bandlimited signal.

LOUDNESS. A level difference between arms is a cue that has nothing to do with
quality, and codec round-trips plus resampling both move peak level. Every clip
on the page — raw included — is peak-normalised after decoding, by the same
function, so loudness cannot separate the arms.

BOUTS UNDER A SECOND ARE EXCLUDED, which 0032 learned live: 21 of its 120 clips
were under a second, Ben reported them ungradeable, and dropping them took the
raw control from 0.87 to 0.96. A clip too short to judge is a coin flip in every
arm and costs power in all of them. Filtered at build time here so the arms stay
balanced, which they do not when it is done afterwards.

Bouts are disjoint from 0028's and 0032's, so nothing is heard twice across any
sitting in this series.
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
from scipy.signal import resample_poly

from crowgpt.codec import Codec, normalise
from crowgpt.dac_codec import DacCodec
from crowgpt.demo import RatingPage
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
PAGE = HERE / "results" / "rate-dac-blind.html"

SPECIES = "american-crow"
PER_ARM = 30
MIN_SECONDS = 1.0
# 0028 took the first 260 one-per-recording bouts (200 ladder + 60 rated) and
# 0032 the next 120. Nothing at or before 380 may be reused.
SKIP = 380
DAC_SR = 44100
SR = 24000


def to_rate(x, source, target):
    if source == target:
        return np.asarray(x, dtype=np.float32)
    g = np.gcd(int(source), int(target))
    return resample_poly(x, int(target) // g, int(source) // g).astype(np.float32)


def main():
    run = Run("0033 — IS DAC GOOD ENOUGH AT A THIRD THE TOKENS",
              ["choose", "encodec", "dac44", "dac24", "page"])
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
            # Skip by POSITION IN THE UNFILTERED LIST, then filter by duration.
            # Filtering first would renumber everything and silently re-serve
            # bouts 0028 and 0032 already played.
            pool = [i for i in ordered[SKIP:]
                    if store.index[i]["n_samples"] / SR >= MIN_SECONDS]
            if len(pool) < PER_ARM * 4:
                raise SystemExit(
                    f"only {len(pool)} unused bouts over {MIN_SECONDS}s past {SKIP}; "
                    f"need {PER_ARM * 4}. Lower PER_ARM rather than reusing bouts."
                )
            pool = pool[: PER_ARM * 4]
            stage.say(f"{len(pool)} bouts, all >= {MIN_SECONDS}s, none used before")

        picks = {name: pool[n * PER_ARM:(n + 1) * PER_ARM]
                 for n, name in enumerate(("raw", "encodec32", "dac44_9", "dac24_32"))}
        clips = []

        def add(arm, position, audio, rate):
            clips.append({"audio": normalise(np.asarray(audio, dtype=np.float32)),
                          "sr": rate, "arm": arm, "bout": int(position),
                          "recording": store.index[position]["recording_id"],
                          "seconds": round(store.index[position]["n_samples"] / SR, 2)})

        with run.stage("encodec") as stage:
            codec = Codec(bandwidth=24.0)
            for position in picks["raw"]:
                add("raw", position, normalise(store.audio(store.index[position])), SR)
            for n, position in enumerate(picks["encodec32"], 1):
                samples = normalise(store.audio(store.index[position]))
                codes = codec.encode(samples).numpy()[0]
                add("encodec32", position, codec.decode(torch.from_numpy(codes))[0], SR)
                stage.update(n, PER_ARM)
            del codec
            torch.cuda.empty_cache()

        with run.stage("dac44") as stage:
            dac = DacCodec(n_codebooks=9, model_type="44khz")
            for n, position in enumerate(picks["dac44_9"], 1):
                samples = normalise(store.audio(store.index[position]))
                up = to_rate(samples, SR, DAC_SR)
                through = dac.roundtrip(up)[0]
                add("dac44_9", position, to_rate(through, DAC_SR, SR), SR)
                stage.update(n, PER_ARM)
            del dac
            torch.cuda.empty_cache()

        with run.stage("dac24") as stage:
            dac = DacCodec(n_codebooks=32, model_type="24khz")
            for n, position in enumerate(picks["dac24_32"], 1):
                samples = normalise(store.audio(store.index[position]))
                add("dac24_32", position, dac.roundtrip(samples)[0], SR)
                stage.update(n, PER_ARM)
            del dac
            torch.cuda.empty_cache()

        with run.stage("page") as stage:
            RatingPage(clips, {
                "Question": "can anything reach raw quality for fewer than 7,200 tokens",
                "Arms": f"raw / EnCodec K=32 / DAC 44k 9cb / DAC 24k 32cb, {PER_ARM} each",
                "Tokens per 3 s": "EnCodec-32 7,200 · DAC-44 ~2,325 · DAC-24 7,200",
                "Model involved": "none — every clip is a real recording",
                "Levels": "every clip peak-normalised after decoding, raw included",
                "Bouts": f">= {MIN_SECONDS}s, disjoint from 0028 and 0032",
            }, seed=0).write(PAGE)
            stage.say(str(PAGE))

        (OUT / "clips.json").write_text(json.dumps(
            [{k: v for k, v in c.items() if k != "audio"} for c in clips], indent=2))
        run.note(f"{len(clips)} trials across 4 arms -> {PAGE}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print("wrote", PAGE)


if __name__ == "__main__":
    main()
