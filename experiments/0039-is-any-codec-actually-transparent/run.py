"""Is any codec actually transparent, asked with an instrument that can say no?

THE CLAIM UNDER TEST is 0034's: DAC-24 at 24 codebooks is "blind-indistinguishable
from raw (0.88 vs 0.92)". That one sentence is the founding fact for
PLAN-TIMBRE's supersession box ("the tokenizer is decided, and it is not
EnCodec"), for 0037's ceiling arithmetic, and for the whole standing account of
where the remaining roughness lives.

It rests on a rating task, and on 2026-08-02 Ben said two things that put it in
doubt. First, by ear, that DAC-24 is "bad too — the best of the worst". Second,
about his own grading: "I marked as good knowing it was AI but it was a good AI
call." RatingPage does write its criterion down, and as rating tasks go it is
carefully worded — but it is still a definition held in the head across 120
clips at 2.3 seconds each, and the second remark is that definition slipping
toward the arm and away from the reference.

WHAT THE SAVED SESSIONS CAN AND CANNOT SETTLE. Three checks were run over every
rating session on disk. Trial-to-trial contrast, matched on arm: -0.012, nothing.
First half against second half: 0.670 vs 0.647, nothing. So the criterion does
not slide *within* a sitting. But all three look for the criterion CHANGING, and
a bar that was stable and simply anchored in the wrong place is invisible to
every one of them. The only cross-session hint is the raw anchor itself, which
is not fixed — 0.85, 0.97, 0.92, 0.92, 0.88, 0.85, 0.87 — and tracks the company
it keeps at r = +0.469 over seven sittings, far short of resolvable at n = 7.

So the question cannot be answered from the saved data, only by a better
instrument.

ABX HAS NO CRITERION TO MISPLACE. Every trial is one bout rendered two ways; X
is a byte-identical copy of one of them; the answer is which. Nothing is good or
bad, real or fake. Chance is exactly 50% and does not depend on anything the
listener believes about what a crow should sound like. **A round-trip that
cannot be beaten above chance is transparent — that is what the word means.**

TWO ARMS, AND THE SECOND ONE IS THE INSTRUMENT CHECK.

  dac24_24   90 trials  the question. 0034 says transparent; the ear now says no.
  encodec8   30 trials  the positive control. 0028 rated this 0.45 against raw's
                        0.85 and Ben has called it scratchy unprompted, so it is
                        a difference known to be audible. If it does NOT come out
                        well above chance the page is broken and the whole
                        sitting is void — which is a thing no previous sitting in
                        this series was able to detect about itself.

WHAT 90 TRIALS BUYS, written before the sitting. The 95% interval on a
proportion is widest at 0.5, where 90 trials give +/-10.3 points. A one-sided
binomial test rejects chance at p < 0.05 from 54/90 (60.0%; 53/90 is p = 0.057
and does not). So this resolves "can he hear it in three trials out of five"
and it cannot resolve a 55% discriminability from 50% — on a perfect 45/90 the
upper bound is still 60.1%. That is the honest limit, and it is the same
limit PLAN-TIMBRE's third instrument lesson describes: an equivalence claim
needs roughly 200 trials, every sitting so far has run 24 to 30, and gates in
this project have been underpowered specifically in the direction that passes.

BOUTS ARE EXCLUDED BY READING THE SAVED SESSIONS, not by skip arithmetic. 0034
selected its pool with `ordered[380:]` then `[120:]`, three hardcoded constants
deep, each one meaning "however many the last experiment happened to take". That
is correct exactly once. Every session file records the bout id of every trial,
so what has been heard is a fact on disk, and this reads it.
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
from crowgpt.dac_codec import DacCodec
from crowgpt.demo import ABXPage
from crowgpt.progress import Run
from crowgpt.tokens import BoutStore

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
OUT = Path(__file__).resolve().parent
PAGE = (HERE / "results" / ("abx-instrument-check.html" if "--instrument-check" in sys.argv
                            else "abx-codec-transparency.html"))
SESSIONS = HERE / "results" / "listening"
# `python run.py --instrument-check` builds a 20-trial anchor-only page instead
# of the full sitting. It answers one question — does ABXPage work at all — and
# nothing else, in about three minutes.
#
# WORTH ASKING FOR EVEN THOUGH THE TOKENIZER QUESTION IS CLOSED. ABXPage is now
# the designated tool for every future transparency or equivalence question in
# this project, and two sittings have failed to demonstrate it can resolve
# anything. If a listener cannot ABX a 2 kHz lowpass then the instrument is
# broken and every measurement it ever takes is worthless; if he can, then the
# codec arms sitting at chance were real findings and the tool is trustworthy
# from here. That has consequences well beyond 0039, which the DAC number no
# longer does.
ANCHOR_ONLY = "--instrument-check" in sys.argv
TRIALS_FILE = "trials-anchor.json" if ANCHOR_ONLY else "trials.json"

SPECIES = "american-crow"
MIN_SECONDS = 1.0
SR = 24000
# THE ANCHOR IS NOT A CODEC, and that is the correction. Attempt 2 used EnCodec
# at 6 kbps as the positive control on the strength of 0028's rating gap (0.45
# against raw's 0.85) — a number produced by the very instrument this experiment
# exists to doubt. Measured independently it was never a large difference:
# log-mel distance from raw is 0.716, against 0.617 for DAC and 0.791 for
# EnCodec at a quarter the bitrate. All three codecs sit in one narrow band. A
# 2 kHz lowpass sits at 5.522 — seven times further out, and unmistakable.
#
# So the anchor is the lowpass. It cannot be inaudible, which is the only
# property a control needs. If Ben cannot ABX it, the page or the playback chain
# is broken and nothing else on the page is readable. If he can, the instrument
# works and a codec arm at chance is a finding rather than a fault.
ARMS = ((("lowpass_2k", 20),) if ANCHOR_ONLY
        else (("dac24_24", 60), ("encodec8", 40), ("lowpass_2k", 20)))


def heard_bouts():
    """Bouts actually played to Ben, from the saved sessions."""
    used = set()
    for path in SESSIONS.glob("*/session-*.json"):
        session = json.loads(path.read_text())
        for trial in session.get("trials", []):
            if trial.get("bout") is not None:
                used.add(int(trial["bout"]))
    return used


def previous_page():
    """The bouts the last built page used, or None if there was no page."""
    path = OUT / TRIALS_FILE
    if not path.exists():
        return None
    return [int(t["bout"]) for t in json.loads(path.read_text())]


def choose_pool(store, need):
    """The bouts for this build.

    A REBUILD MUST NOT COST BOUTS. The first version retired anything that had
    ever been built into a page. That is right for a page that was sat and wrong
    for one thrown away: three rebuilds chasing a JavaScript bug burned 360
    unheard bouts and took the pool from 803 down to a single spare. Held-out
    American Crow, one bout per recording, over a second long, never heard, is a
    finite resource and the scarcest one this experiment consumes — fixing a
    bug must be free against it.

    So the rule is by HEARING, not by building. A page whose bouts appear in no
    saved session was never sat, and is reissued exactly as it was. A page that
    was even partly sat is retired whole, because the post-answer reveal names
    the arm and he may have seen any of them.
    """
    heard = heard_bouts()
    previous = previous_page()
    if previous and not (set(previous) & heard):
        return previous, "reissued unchanged — the last build was never sat"

    retire = heard | set(previous or ())
    seen, pool = set(), []
    for i in store.split(seed=0)["test"]:
        row = store.index[i]
        if row["species"] != SPECIES or i in retire:
            continue
        if row["recording_id"] in seen or row["n_samples"] / SR < MIN_SECONDS:
            continue
        seen.add(row["recording_id"])
        pool.append(i)
    if len(pool) < need:
        raise SystemExit(
            f"only {len(pool)} unheard bouts over {MIN_SECONDS}s remain; need {need}. "
            f"Lower the trial counts rather than reusing bouts — a bout Ben has "
            f"already heard is one he may recognise."
        )
    return pool[:need], f"{len(pool)} available, {len(retire)} retired"


def make_treatment(name):
    """A function raw -> treated, and whether it needs the GPU freed afterwards."""
    if name == "lowpass_2k":
        from scipy.signal import butter, sosfilt

        sos = butter(8, 2000, "lowpass", fs=SR, output="sos")
        return (lambda x: sosfilt(sos, x).astype(np.float32)), None
    codec = (DacCodec(n_codebooks=24, model_type="24khz") if name == "dac24_24"
             else Codec(bandwidth=6.0))
    return (lambda x: np.asarray(codec.roundtrip(x)[0], dtype=np.float32)), codec


def build_arm(name, picks, store, stage, done, total):
    treat, codec = make_treatment(name)
    trials = []
    for position in picks:
        row = store.index[position]
        samples = normalise(store.audio(row))
        treated = treat(samples)
        # Length can come back a frame long; ABX on two different durations is
        # answerable by clock rather than by ear.
        treated = treated[: samples.size]
        trials.append({
            "reference": samples,
            "treated": normalise(treated),
            "sr": SR,
            "arm": name,
            "bout": int(position),
            "recording": row["recording_id"],
            "seconds": round(row["n_samples"] / SR, 2),
        })
        stage.update(done + len(trials), total, extra=name)
    if codec is not None:
        del codec
        torch.cuda.empty_cache()
    return trials


def main():
    run = Run("0039 — IS ANY CODEC ACTUALLY TRANSPARENT",
              ["choose", "decode", "page"])
    try:
        store = BoutStore(DATA / "bouts")
        need = sum(count for _, count in ARMS)

        with run.stage("choose") as stage:
            pool, how = choose_pool(store, need)
            stage.say(f"{len(pool)} bouts — {how}")

        trials = []
        with run.stage("decode") as stage:
            cursor = 0
            for name, count in ARMS:
                picks = pool[cursor:cursor + count]
                cursor += count
                trials += build_arm(name, picks, store, stage, len(trials), need)

        with run.stage("page") as stage:
            page = ABXPage(
                trials,
                {
                    "Question": ("does this instrument work at all"
                                 if ANCHOR_ONLY else "is the round-trip audible at all"),
                    "Arms": ("2 kHz lowpass only — an instrument check, not a codec test"
                             if ANCHOR_ONLY
                             else "DAC-24 24cb (60) · EnCodec 6 kbps (40) · 2 kHz lowpass (20, anchor)"),
                    "Chance": "50% — X is a copy of A or of B",
                    "Resolves": "63% (DAC, n=60) · 65% (EnCodec, n=40) · 75% (anchor, n=20)",
                    "Cannot resolve": "a 55% tell from 50% — that needs ~200 trials",
                    "Corpus": f"{SPECIES}, held-out test split, one bout per recording",
                    "Never heard before": "every bout is new to this sitting",
                },
                seed=39,
                title="Which one is X?",
                # Per arm, not globally: each arm is scored against chance
                # separately, so it is the per-arm rate a response bias moves.
                balance_by="arm",
            )
            page.write(PAGE)
            (OUT / TRIALS_FILE).write_text(json.dumps(
                [{k: v for k, v in t.items() if k not in ("reference", "treated")}
                 for t in trials], indent=2))
            stage.say(f"{PAGE.relative_to(HERE)} — {len(trials)} trials")

        run.note(f"{len(trials)} ABX trials -> {PAGE}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise
    print("wrote", PAGE)


if __name__ == "__main__":
    main()
