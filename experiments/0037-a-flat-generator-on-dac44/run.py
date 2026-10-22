"""Does the best quality-per-token codec make a better generator?

The last route left after 0035 killed the extender. Overnight; `make watch`
or the field server's Training panel says where it is.

THE OPENING. Five sittings established the codec ceilings by ear, and they are
very far apart:

    EnCodec 8 cb    1,811 tokens/3s    ceiling 0.45   (0028)
    DAC-44 9 cb     2,325 tokens/3s    ceiling 0.80   (0033)
    DAC-24 24 cb    5,400 tokens/3s    ceiling 0.88   (0034)

The incumbent generator lives on the first row, at 0.25 against that 0.45
ceiling (0030). The third row is unreachable: 5,400 tokens is triple what the
generator handles, and 0035 killed the extender that was meant to reach it.

**The middle row has never been trained on**, and it is the interesting one: 28%
more tokens than the generator already copes with, for a ceiling 35 points
higher. 0017 measured DAC-44's spectral distance below EnCodec's at maximum
bandwidth, and rejected it anyway — on retention at matched token count, a
constraint that expired when transparency turned out to cost more than 1,800
tokens.

ONE VARIABLE. This matches `model-fair-k8` from 0030 exactly — d384/L8/H6,
effective batch 18, dropout 0, 30,000 steps — so the tokenizer is the only
difference between the two generators. 0030 is where that discipline came from:
comparing against the incumbent instead would have moved bandwidth, dropout and
batch together.

THE THING THIS COULD STILL LOSE TO. 0018 and 0030 both found that a longer
sequence costs more than a higher ceiling returns. But both measured it where
the ceiling barely moved — EnCodec at 8 and 16 codebooks are indistinguishable
by ear. Here the sequence grows 29% and the ceiling grows 35 points, which is a
different trade entirely. If it still loses, the sequence-length effect is
stronger than anyone has credited and that is worth knowing plainly.

THE TRAP THIS AVOIDS. DAC's 44 kHz model does not resample and does not say so:
handed 24 kHz audio it reinterprets rather than converts, pitching a caw up by
1.84x while every stage downstream looks fine. `Resampled` wraps the codec so
audio goes in and comes back at the corpus rate, and the manifest records the
pairing so a Sampler cannot rebuild half of it.
"""
import json
import sys
from collections import Counter
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
TOKENS = DATA / "tokens-dac44"
RESULTS = HERE / "results"
MODEL = RESULTS / "model-dac44"
CONTROL = RESULTS / "model-fair-k8"     # 0030's arm, same recipe, EnCodec 8 cb
PAGE = RESULTS / "rate-dac44-gen-blind.html"
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
N_CODEBOOKS = 9
STEPS = 30_000
MICRO_BATCH = 9      # 18 OOMs at this shape; 12 peaks at 9.3 GiB, 9 leaves headroom
ACCUMULATE = 2       # effective 18, matching model-fair-k8
MAX_FRAMES = 260     # DAC-44 runs at 86.13 fps, so 3 s is 258 frames, not 225
PER_ARM = 24
MIN_SECONDS = 1.0
SKIP = 380
ALREADY_USED = 240 + 72   # 0033 and 0034 took 120 each; 0035 took 72
SR = 24000


def tokenize(run):
    with run.stage("tokenize") as stage:
        if (TOKENS / "manifest.json").exists():
            stage.say("already on disk")
            return
        from crowgpt.dac_codec import DacCodec, Resampled
        from crowgpt.tokens import BoutStore, TokenWriter

        store = BoutStore(BOUTS)
        splits = store.split(seed=0)
        offsets, running = {}, 0
        for name in splits:
            offsets[name] = running
            running += len(splits[name])
        total = running
        codec = Resampled(DacCodec(n_codebooks=N_CODEBOOKS, model_type="44khz"), SR)
        stage.say(f"{len(store)} bouts -> {TOKENS} at {codec.kind}")
        manifest = TokenWriter(store, TOKENS, codec=codec).run(
            splits, on_progress=lambda split, done, _n: stage.update(
                offsets[split] + done, total, extra=split))
        run.note(f"tokenised {manifest['codec']} K={manifest['n_codebooks']} "
                 f"vocab {manifest['vocab_size']}")


def train(run):
    with run.stage("train") as stage:
        if (MODEL / "history.json").exists():
            stage.say("already trained")
            return
        from crowgpt.train import Trainer

        trainer = Trainer(
            TOKENS, MODEL,
            steps=STEPS,
            batch_size=MICRO_BATCH,
            accumulate=ACCUMULATE,
            dropout=0.0,
            n_layer=8, n_head=6, n_embd=384,
            memory_budget=10**10,
            eval_every=500,
        )
        if trainer.effective_batch != 18:
            raise SystemExit(
                f"effective batch {trainer.effective_batch}, expected 18 — "
                f"no longer comparable to model-fair-k8"
            )
        dropped = len(trainer.train_set) - len(trainer.train_batcher.usable)
        if dropped:
            raise SystemExit(f"{dropped} sequences exceed the block; raise it")
        stage.say(f"effective batch {trainer.effective_batch}, "
                  f"block {trainer.config.block_size}")
        last = {"text": "no eval yet"}

        def note_eval(step, val):
            last["text"] = f"val {val:.4f}"
            stage.update(step, STEPS, extra=last["text"])

        history = trainer.run(
            on_eval=note_eval,
            on_step=lambda step, total: stage.update(step, total, extra=last["text"]),
        )
        run.note(f"dac44 generator best val {history['best_val']:.4f} "
                 f"(NOT comparable to any other codec's loss — different vocabulary)")


def generate(run):
    with run.stage("generate") as stage:
        from crowgpt.codec import normalise
        from crowgpt.sample import Sampler
        from crowgpt.segment import Segmenter
        from crowgpt.tokens import BoutStore

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
        long_enough = [i for i in ordered[SKIP:]
                       if store.index[i]["n_samples"] / SR >= MIN_SECONDS]
        pool = long_enough[ALREADY_USED:]
        if len(pool) < PER_ARM:
            raise SystemExit(f"only {len(pool)} unused bouts remain, need {PER_ARM}")

        arms = {"real": [normalise(store.audio(store.index[i])) for i in pool[:PER_ARM]]}
        stage.update(PER_ARM, PER_ARM * 3, extra="real")

        done = PER_ARM
        for name, folder in (("dac44_gen", MODEL), ("fairk8_gen", CONTROL)):
            sampler = Sampler(folder / "model.pt", token_dir=None)
            made = []
            for i in range(PER_ARM):
                made.append(sampler.audio(SPECIES, temperature=1.0, top_k=200,
                                          seed=2000 + i, max_frames=MAX_FRAMES))
                done += 1
                stage.update(done, PER_ARM * 3, extra=f"{name} {i + 1}/{PER_ARM}")
            arms[name] = made
            del sampler
            torch.cuda.empty_cache()

        segmenter = Segmenter()
        units = {}
        for name, clips in arms.items():
            counts = [len(segmenter.segment(np.asarray(c, dtype=np.float32), SR)[1])
                      for c in clips]
            units[name] = {"mean_units": round(float(np.mean(counts)), 2),
                           "single_unit_share": round(float((np.array(counts) <= 1).mean()), 3),
                           "histogram": {str(k): v for k, v in sorted(Counter(counts).items())}}
        (OUT / "units.json").write_text(json.dumps(units, indent=2))
        run.note("units/bout — " + " · ".join(
            f"{n}={units[n]['mean_units']}" for n in ("real", "dac44_gen", "fairk8_gen")))
        return arms


def page(run, arms):
    with run.stage("page") as stage:
        from crowgpt.codec import normalise
        from crowgpt.demo import RatingPage

        clips = [{"audio": normalise(np.asarray(a, dtype=np.float32)), "sr": SR,
                  "arm": name, "n": i}
                 for name, group in arms.items() for i, a in enumerate(group)]
        RatingPage(clips, {
            "Question": "does the better codec make a better generator",
            "Arms": f"real / DAC-44 9cb generated / EnCodec 8cb generated, {PER_ARM} each",
            "Recipe": "both models d384 L8 H6, effective batch 18, dropout 0, "
                      "30,000 steps — the tokenizer is the only difference",
            "Ceilings": "DAC-44 9cb 0.80 (0033) · EnCodec 8cb 0.45 (0028)",
            "Levels": "every clip peak-normalised, real included",
        }, seed=0).write(PAGE)
        (OUT / "clips.json").write_text(json.dumps(
            [{k: v for k, v in c.items() if k != "audio"} for c in clips], indent=2))
        stage.say(str(PAGE))
        run.note(f"page ready: {PAGE}")


def main():
    run = Run("0037 — A FLAT GENERATOR ON DAC-44",
              ["tokenize", "train", "generate", "page"])
    try:
        tokenize(run)
        train(run)
        page(run, generate(run))
        run.note("DONE — rate rate-dac44-gen-blind.html")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
