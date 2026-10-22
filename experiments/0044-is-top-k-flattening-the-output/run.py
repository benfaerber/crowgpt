"""Is top_k flattening the output, and does a channel token help?

Two questions in one sitting, because Ben's ears are the scarcest resource in
this project and `PairPage` balances sides within each pairing separately.

THE FIRST QUESTION IS THE URGENT ONE. `top_k=200` is not a uniform truncation.
Measured per stage on `model-fair-k8`, top-200 of 1024 retains 0.981 of the
probability mass at codebook 0 and 0.782 at codebook 7 — a no-op on coarse
structure that discards a fifth of the fine residual and renormalises onto
whichever 200 codes the model happens to rank highest. That is structurally the
same operation as cooling the fine stages, which `stages.py` pre-registered as
the thing that would "make the sampler re-pick the same arbitrary residual code
over and over, which is periodic, and periodic is what 'robotic' sounds like".

It has never been judged by ear at the shipped temperature. 0019 closed per-stage
TEMPERATURE on calibration grounds and checked top-k only against EOS, never
against mass. 0015 swept top-k on/off at five temperatures and found it hurt at
every one EXCEPT 1.00 — which is the setting the project ships — and its evidence
was BirdNET detection, which 0014 established cannot hear quality at all.

0043 measured both arms offline: turning top-k off puts frame-to-frame timbre
change at 0.0422 against real audio's 0.0413, and within-clip spread at 0.0620
against 0.0572, neither resolved from real, where `top_k=200` sits resolved
BELOW both. But that instrument only says the timbre MOVES like real timbre. It
cannot say the clip sounds like a crow, and it reversed sign between two
checkpoints of the same model, so it does not get to decide this alone.

THE SECOND QUESTION IS THE CHANNEL TOKEN. 0042 measured that the microphone moves
timbre 6.2x further than everything inside one recording, and the generator has
no token for it. `model-channel256` is `model-fair-k8`'s exact recipe plus a
prefix token naming one of 256 background-spectrum buckets. Sampling pins ONE
bucket, because drawing it per clip would hand back the averaging it exists to
remove. Both arms of this pairing run at `top_k=200` so the model is the only
difference; whichever way the first question goes, this one is still answerable.

BOTH PAIRINGS ARE MODEL-VS-MODEL. Real appears only as catch trials, scored
separately and excluded from every comparison — 0041's rule, and Ben's objection
that produced it: real rates 0.85-0.97 and generated 0.22, so pairing them tests
nothing except whether the listener is awake.

REAL BOUTS ARE CONSUMED, NOT REUSED. `ALREADY_USED` tracks how many held-out
American Crow bouts previous sittings have spent, so a catch trial never carries
audio Ben has already judged in another context.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim  # noqa: E402

claim()

import numpy as np  # noqa: E402
import torch  # noqa: E402

from crowgpt.progress import Run  # noqa: E402

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
BOUTS = DATA / "bouts"
TOKENS = DATA / "tokens"
RESULTS = HERE / "results"
PAGE = RESULTS / "rate-topk-blind.html"
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
INCUMBENT = RESULTS / "model-fair-k8"
CHANNELLED = RESULTS / "model-channel256"
MAX_FRAMES = 225
N_TOPK, N_CHANNEL, N_CATCH = 30, 20, 10
# Applies to EVERY arm, generated included — that is the fix. Seed blocks are
# 500 apart so an over-drawing arm cannot run into the next arm's seeds and
# pair a clip against its own near-copy.
MIN_SECONDS = 1.0
MAX_OVERDRAW = 4
SR = 24000
SKIP = 380
# 0033 120, 0034 120, 0035 72, 0037 24, 0038 24, 0041 10
ALREADY_USED = 370


def generate(sampler, count, top_k, first_seed, on_clip, channel=None):
    """`count` clips of at least MIN_SECONDS, over-drawing until it has them.

    SHORT CLIPS ARE UNGRADEABLE AND THIS IS THE SECOND TIME IT HAS BITTEN.
    PLAN-TIMBRE recorded it as a protocol fix found live — "clips under 1 second
    are ungradeable; filtering them took a raw control from 0.87 to 0.96, so
    filter at build time, not after" — and the first build of this page applied
    MIN_SECONDS to the real catch bouts only. Generated arms went through
    unfiltered and the shortest was 0.08 s. Ben found it in the grader.

    Generated bouts are short far more often than real ones (0024: 1.37 units
    per bout against 3.37), so the generated side is exactly where the filter is
    needed. Over-drawing rather than accepting what comes keeps every arm at its
    stated n instead of silently shrinking the one that stops early.

    THE DISCARD RATE IS ITSELF A MEASUREMENT and is returned, because "how often
    does this arm stop early" is a real difference between arms and throwing the
    short ones away without counting them would hide it.
    """
    from crowgpt.codec import normalise

    out, drawn = [], 0
    while len(out) < count:
        if drawn >= count * MAX_OVERDRAW:
            raise SystemExit(
                f"drew {drawn} clips for {count} usable at top_k={top_k}; "
                f"the arm stops early far more often than MAX_OVERDRAW allows")
        audio = np.asarray(
            sampler.audio(SPECIES, temperature=1.0, top_k=top_k,
                          seed=first_seed + drawn, max_frames=MAX_FRAMES,
                          **({"channel": channel} if channel else {})),
            dtype=np.float32)
        drawn += 1
        if audio.size / SR < MIN_SECONDS:
            continue
        out.append(normalise(audio))
        on_clip()
    return out, drawn


def main():
    run = Run("0044 — IS TOP-K FLATTENING THE OUTPUT",
              ["generate", "real", "page"])
    try:
        from crowgpt.codec import normalise
        from crowgpt.sample import Sampler
        from crowgpt.tokens import BoutStore

        made, drew = {}, {}
        total = N_TOPK * 2 + N_CHANNEL * 2 + N_CATCH * 2
        with run.stage("generate") as stage:
            done = 0

            def tick(name):
                def bump():
                    nonlocal done
                    done += 1
                    stage.update(done, total, extra=name)
                return bump

            sampler = Sampler(INCUMBENT / "model.pt", token_dir=str(TOKENS))
            # Distinct seed blocks per arm, so no two arms are the same draw with
            # one knob changed — that would pair a clip against a near-copy of
            # itself and understate every difference.
            # N_TOPK + N_CATCH, because the catch trials must carry clips the
            # listener has not already judged in the top-k pairing. Showing the
            # same clip twice in one sitting is a second look, not a second
            # trial.
            made["topk200"], drew["topk200"] = generate(
                sampler, N_TOPK + N_CATCH, 200, 7000, tick("topk200"))
            made["notopk"], drew["notopk"] = generate(
                sampler, N_TOPK, None, 7500, tick("notopk"))
            made["fairk8"], drew["fairk8"] = generate(
                sampler, N_CHANNEL, 200, 8000, tick("fairk8"))
            del sampler
            torch.cuda.empty_cache()

            channelled = Sampler(CHANNELLED / "model.pt", token_dir=str(TOKENS))
            pinned = channelled.vocabulary.channels[0]
            made["channel256"], drew["channel256"] = generate(
                channelled, N_CHANNEL, 200, 8500, tick("channel256"), channel=pinned)
            del channelled
            torch.cuda.empty_cache()
            kept = " · ".join(f"{k} {len(made[k])}/{drew[k]}" for k in drew)
            stage.say(f"{done} clips · channel pinned to {pinned} · kept/drawn {kept}")
            run.note("clips at least "
                     f"{MIN_SECONDS}s, kept/drawn: {kept}")

        with run.stage("real") as stage:
            store = BoutStore(BOUTS)
            splits = store.split(seed=0)
            held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
            seen, ordered = set(), []
            for i in held:
                recording = store.index[i]["recording_id"]
                if recording in seen:
                    continue
                seen.add(recording)
                ordered.append(i)
            pool = [i for i in ordered[SKIP:]
                    if store.index[i]["n_samples"] / SR >= MIN_SECONDS][ALREADY_USED:]
            if len(pool) < N_CATCH:
                raise SystemExit(f"only {len(pool)} unused bouts remain, need {N_CATCH}")
            made["real"] = [normalise(store.audio(store.index[i])) for i in pool[:N_CATCH]]
            stage.say(f"{N_CATCH} catch bouts, {len(pool)} unused remain")

        with run.stage("page") as stage:
            from crowgpt.demo import PairPage

            def clip(name, i):
                return {"audio": made[name][i], "sr": SR, "arm": name}

            pairs = []
            for i in range(N_TOPK):
                pairs.append({"a": clip("topk200", i), "b": clip("notopk", i)})
            for i in range(N_CHANNEL):
                pairs.append({"a": clip("fairk8", i), "b": clip("channel256", i)})
            for i in range(N_CATCH):
                pairs.append({"a": clip("real", i),
                              "b": clip("topk200", N_TOPK + i), "catch": True})

            PairPage(pairs, {
                "Question": "which of two clips is less robotic",
                "Pairs": f"{N_TOPK} top_k=200 vs top_k=None (the open question) · "
                         f"{N_CHANNEL} fairk8 vs channel256 (both top_k=200) · "
                         f"{N_CATCH} real vs generated (catch, scored separately)",
                "Why top-k": "it keeps 98.1% of the probability mass at codebook 0 "
                             "and 78.2% at codebook 7 — a no-op on structure that "
                             "discards a fifth of the fine residual",
                "Why channel": "0042 measured the microphone moving timbre 6.2x "
                               "further than anything inside one recording, and the "
                               "model had no token for it",
                "Sides": "balanced within each pairing and recorded, so a "
                         "left-button habit cannot read as a model preference",
                "Levels": "every clip peak-normalised",
                "Lengths": f"every clip at least {MIN_SECONDS}s — generated arms "
                           f"over-drawn to hold n, discard rates "
                           + " · ".join(f"{k} {drew[k] - len(made[k])}" for k in drew),
            }, seed=0).write(PAGE)
            (OUT / "pairs.json").write_text(json.dumps(
                [{"a": p["a"]["arm"], "b": p["b"]["arm"], "catch": p.get("catch", False)}
                 for p in pairs], indent=2))
            stage.say(str(PAGE))
            run.note(f"{len(pairs)} pairs -> {PAGE}")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
