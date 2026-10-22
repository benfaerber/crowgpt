"""Does the delay pattern help? The last untried modelling idea.

Overnight run for 2026-08-04. `make watch`, or the field server's
Training panel, says where it is.

EVERY OTHER ROUTE IS CLOSED. The tokenizer took four configurations and moved
nothing (0028, 0032-0037). Capacity was ruled out twice, at two sequence lengths
(0023, 0038). Shortening the sequence hurt badly (0038). The extender died on
DAC's near-white fine stages (0035). What has never been varied is the OBJECTIVE:
every model in this project has been next-token cross-entropy over a flat
interleaved stream.

WHY FLAT IS THE SUSPECT. At position (t, k) the model predicts codebook k of
frame t from codebooks 0..k-1 of the SAME frame plus everything before. So the
fine stages hang off a coarse prediction made three tokens earlier and errors
compound inside a frame, which is a plausible shape for "right structure, wrong
texture" — 0027's description of the defect. MusicGen reports flat interleaving
as the worst of its four layouts and the delay pattern as the fix.

Under the delay, stage k carries frame t-k, so every prediction has a FULL FRAME
of history behind it rather than a few tokens of the frame it belongs to.

EDGE-CLAMPED, NOT PADDED. A PAD id would cost a vocabulary entry, a change to
`Vocabulary.allowed`, a change to `LegalMask` and a new way for generation to
emit something illegal. Clamping the head to frame 0 keeps the stream exactly
K-periodic with the same vocabulary and the same mask, so nothing downstream
knows this happened. `tests/test_delay_pattern.py` holds the round trip exact at
every length including 1 frame, because a delay applied backwards still decodes.

ONE VARIABLE. Matched to `model-fair-k8` exactly — d384/L8/H6, effective batch
18, dropout 0, 30,000 steps, same corpus, same codec at 8 codebooks. Only the
token layout moves. The run aborts if the effective batch drifts off 18.

THE SITTING IS FORCED-CHOICE, 60 PAIRS. 0041's instrument, which reproduced a
known answer and resolves roughly a 13-point difference at this size against the
~20 of a 30-pair sitting and the ~28 of absolute rating at 24 an arm. Sides are
balanced within the pairing by construction (0041 measured a 65% left bias).

CLIPS UNDER A SECOND ARE DROPPED BEFORE PAIRING. Ben after 0044: "too short clips
instantly loose. 0.1 second is always worse." Generated bouts run from 0.08 s, so
about one trial in six was being decided by length rather than timbre. 0032
established the same rule for real bouts and it was never applied to the
generated side.
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

from crowgpt.progress import Run

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
BOUTS = DATA / "bouts"
TOKENS = DATA / "tokens-delay"
RESULTS = HERE / "results"
MODEL = RESULTS / "model-delay"
CONTROL = RESULTS / "model-fair-k8"
PAGE = RESULTS / "rate-delay-blind.html"
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
STEPS = 30_000
MICRO_BATCH, ACCUMULATE = 18, 1
N_PAIRS, N_CATCH = 60, 10
MIN_SECONDS = 1.0
MAX_BLOCKS = 232          # 225 frames + the K-1 the delay adds
SKIP, ALREADY_USED = 380, 380
SR = 24000


def tokenize(run):
    with run.stage("tokenize") as stage:
        if (TOKENS / "manifest.json").exists():
            stage.say("already on disk")
            return
        from crowgpt.codec import Codec
        from crowgpt.dac_codec import Delayed
        from crowgpt.tokens import BoutStore, TokenWriter

        store = BoutStore(BOUTS)
        splits = store.split(seed=0)
        offsets, running = {}, 0
        for name in splits:
            offsets[name] = running
            running += len(splits[name])
        codec = Delayed(Codec(bandwidth=6.0))
        stage.say(f"{len(store)} bouts -> {TOKENS} as {codec.kind}")
        manifest = TokenWriter(store, TOKENS, codec=codec).run(
            splits, on_progress=lambda split, done, _n: stage.update(
                offsets[split] + done, running, extra=split))
        run.note(f"tokenised {manifest['codec']} vocab {manifest['vocab_size']}")


def train(run):
    with run.stage("train") as stage:
        if (MODEL / "history.json").exists():
            stage.say("already trained")
            return
        from crowgpt.train import Trainer

        trainer = Trainer(TOKENS, MODEL, steps=STEPS, batch_size=MICRO_BATCH,
                          accumulate=ACCUMULATE, dropout=0.0,
                          n_layer=8, n_head=6, n_embd=384,
                          memory_budget=10**10, eval_every=500)
        if trainer.effective_batch != 18:
            raise SystemExit(f"effective batch {trainer.effective_batch}, expected 18 — "
                             f"no longer comparable to model-fair-k8")
        dropped = len(trainer.train_set) - len(trainer.train_batcher.usable)
        if dropped:
            raise SystemExit(f"{dropped} sequences exceed the block; raise it")
        stage.say(f"{trainer.model.n_params()/1e6:.1f}M params, "
                  f"block {trainer.config.block_size}, batch {trainer.effective_batch}")
        last = {"text": "no eval yet"}

        def note_eval(step, val):
            last["text"] = f"val {val:.4f}"
            stage.update(step, STEPS, extra=last["text"])

        history = trainer.run(on_eval=note_eval,
                              on_step=lambda s, t: stage.update(s, t, extra=last["text"]))
        run.note(f"delay best val {history['best_val']:.4f} "
                 f"(NOT comparable to a flat run's loss — different token layout)")


def long_enough(sampler, count, first_seed, on_clip, max_blocks):
    """`count` clips of at least MIN_SECONDS, skipping the fragments.

    Draws past `count` rather than accepting what comes, because a short clip is
    answered on length. Recorded how many were skipped: if that fraction differs
    between arms it is itself a finding about the model, not a nuisance.
    """
    from crowgpt.codec import normalise

    kept, skipped, i = [], 0, 0
    while len(kept) < count and i < count * 8:
        audio = sampler.audio(SPECIES, temperature=1.0, top_k=200,
                              seed=first_seed + i, max_frames=max_blocks)
        i += 1
        if len(audio) / SR >= MIN_SECONDS:
            kept.append(normalise(np.asarray(audio, dtype=np.float32)))
            on_clip()
        else:
            skipped += 1
    if len(kept) < count:
        raise SystemExit(f"only {len(kept)} clips over {MIN_SECONDS}s in {i} draws")
    return kept, skipped


def generate(run):
    with run.stage("generate") as stage:
        from crowgpt.codec import normalise
        from crowgpt.sample import Sampler
        from crowgpt.tokens import BoutStore

        made, skips, done = {}, {}, 0
        total = N_PAIRS * 2 + N_CATCH

        def tick():
            nonlocal done
            done += 1
            stage.update(done, total)

        for name, folder, blocks in (("delay", MODEL, MAX_BLOCKS),
                                     ("fairk8", CONTROL, 225)):
            sampler = Sampler(folder / "model.pt", token_dir=None)
            made[name], skips[name] = long_enough(sampler, N_PAIRS, 9000, tick, blocks)
            del sampler
            torch.cuda.empty_cache()

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
        done += N_CATCH
        stage.update(done, total, extra="real")

        run.note("fragments skipped (<1s) — " + " · ".join(
            f"{k}={v}" for k, v in skips.items()))
        (OUT / "skipped.json").write_text(json.dumps(skips, indent=2))
        return made


def page(run, made):
    with run.stage("page") as stage:
        from crowgpt.demo import PairPage

        def clip(name, i):
            return {"audio": made[name][i], "sr": SR, "arm": name}

        pairs = [{"a": clip("delay", i), "b": clip("fairk8", i)} for i in range(N_PAIRS)]
        pairs += [{"a": clip("real", i), "b": clip("fairk8", N_PAIRS - 1 - i),
                   "catch": True} for i in range(N_CATCH)]
        PairPage(pairs, {
            "Question": "does the delay pattern sound less robotic than flat",
            "Pairs": f"{N_PAIRS} delay vs fairk8 · {N_CATCH} real vs fairk8 (catch)",
            "One variable": "both models d384 L8 H6, effective batch 18, dropout 0, "
                            "30,000 steps, EnCodec 8 codebooks — only the token "
                            "layout differs",
            "Clips": f"all >= {MIN_SECONDS}s; fragments dropped before pairing",
            "Sides": "balanced within the pairing, not randomised (0041)",
        }, seed=0).write(PAGE)
        (OUT / "pairs.json").write_text(json.dumps(
            [{"a": p["a"]["arm"], "b": p["b"]["arm"], "catch": p.get("catch", False)}
             for p in pairs], indent=2))
        stage.say(str(PAGE))
        run.note(f"{len(pairs)} pairs -> {PAGE}")


def main():
    run = Run("0045 — DOES THE DELAY PATTERN HELP",
              ["tokenize", "train", "generate", "page"])
    try:
        tokenize(run)
        train(run)
        page(run, generate(run))
        run.note("DONE — rate rate-delay-blind.html")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
