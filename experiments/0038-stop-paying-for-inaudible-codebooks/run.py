"""Does dropping three inaudible codebooks make the model better?

The overnight run for 2026-08-02. `make watch`, or the field server's
Training panel, says where it is.

THE ONE MOVE THAT MAKES THE MODEL'S JOB EASIER. Everything tried today made it
harder — more codebooks, denser tokens, whiter residuals — and every time the
model gave back more than the tokenizer won:

    0030  more EnCodec codebooks        no audible gain
    0035  extender on DAC               0/24, fine stages at 9.935 bits
    0037  better codec end to end       no resolvable gain, 0.25 vs 0.21

0037 measured why: EnCodec-8's marginal is 8.983 bits and the model recovers
2.365; DAC-44's is 9.554 and it recovers 1.401. A codec that packs more into
each token leaves less for a sequence model. So the lever is not a better codec.

0024 WROTE DOWN THE OPPOSITE MOVE AND NOBODY DID IT. Replacing codebooks 5-7
with draws from the codec's own marginals is INAUDIBLE — measured by ear, with
real rows as the control. Its own conclusion: "A 3-second bout at 75 fps is
1,800 tokens at eight codebooks and 1,125 at five, and attention is quadratic —
roughly 61% less attention compute per bout... Every training run in this
project has been paying for three stages that a listener cannot hear."

So train on five. Same audible content, 62% of the sequence.

TWO ARMS, because they answer different questions and only the second is new.

    k5_matched   d384/L8/H6, effective batch 18 — the same recipe as
                 model-fair-k8. Isolates "does a shorter sequence help at fixed
                 capacity?" Note it lands at 16.6M params against fair-k8's
                 ~21.9M: the architecture is identical and the embedding is
                 smaller because the vocabulary is, which is part of what
                 "five codebooks" means rather than a confound to remove.

    k5_bigger    d512/L12/H8, 41M params, effective batch 18 — spends the
                 sequence saving on capacity. This is 0023's question asked
                 properly: it concluded "more capacity is NOT the evidenced next
                 move" because capacity bought loss and not audible quality, but
                 that was capacity on the SAME objective at the SAME length.
                 Here the length is cheaper first.

GENERATION FILLS STAGES 5-7 FROM THE MARGINAL, which is exactly the arm 0024
proved inaudible — not dropped. Decoding five rows is a lower bitrate by
construction and would compare a model change against a bandwidth change. The
marginals are measured from training bouts here rather than assumed.

THE WAY THIS COULD MISLEAD. 0024's inaudibility result was collected on the
incumbent's output. A 5-codebook model is a different distribution, and the
marginal fill could interact with it in a way three stages of the incumbent's
did not. k5_matched against fairk8 is the arm that would show that, because
both are the same recipe and only the codebook count moves.
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
TOKENS = DATA / "tokens-k5"
RESULTS = HERE / "results"
MATCHED = RESULTS / "model-k5-matched"
BIGGER = RESULTS / "model-k5-bigger"
CONTROL = RESULTS / "model-fair-k8"
PAGE = RESULTS / "rate-k5-blind.html"
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
KEEP = 5
FULL = 8
STEPS = 30_000
ARMS = (
    ("k5_matched", MATCHED, dict(n_embd=384, n_layer=8, n_head=6), 18, 1),
    ("k5_bigger", BIGGER, dict(n_embd=512, n_layer=12, n_head=8), 9, 2),
)
PER_ARM = 24
MIN_SECONDS = 1.0
SKIP = 380
ALREADY_USED = 336   # 0033 120, 0034 120, 0035 72, 0037 24
MAX_FRAMES = 230
SR = 24000


def tokenize(run):
    with run.stage("tokenize") as stage:
        if (TOKENS / "manifest.json").exists():
            stage.say("already on disk")
            return
        from crowgpt.codec import Codec
        from crowgpt.tokens import BoutStore, TokenWriter

        store = BoutStore(BOUTS)
        splits = store.split(seed=0)
        offsets, running = {}, 0
        for name in splits:
            offsets[name] = running
            running += len(splits[name])
        total = running
        stage.say(f"{len(store)} bouts -> {TOKENS} at {KEEP} codebooks")
        manifest = TokenWriter(store, TOKENS,
                               codec=Codec(bandwidth=6.0, keep=KEEP)).run(
            splits, on_progress=lambda split, done, _n: stage.update(
                offsets[split] + done, total, extra=split))
        run.note(f"tokenised K={manifest['n_codebooks']} vocab {manifest['vocab_size']}")


def train(run, name, out_dir, shape, micro, accumulate):
    with run.stage(name) as stage:
        if (out_dir / "history.json").exists():
            stage.say("already trained")
            return
        from crowgpt.train import Trainer

        trainer = Trainer(
            TOKENS, out_dir, steps=STEPS, batch_size=micro, accumulate=accumulate,
            dropout=0.0, memory_budget=10**10, eval_every=500, **shape)
        if trainer.effective_batch != 18:
            raise SystemExit(
                f"{name}: effective batch {trainer.effective_batch}, expected 18")
        dropped = len(trainer.train_set) - len(trainer.train_batcher.usable)
        if dropped:
            raise SystemExit(f"{name}: {dropped} sequences exceed the block")
        stage.say(f"{trainer.model.n_params()/1e6:.1f}M params, "
                  f"batch {trainer.effective_batch}, block {trainer.config.block_size}")
        last = {"text": "no eval yet"}

        def note_eval(step, val):
            last["text"] = f"val {val:.4f}"
            stage.update(step, STEPS, extra=last["text"])

        history = trainer.run(
            on_eval=note_eval,
            on_step=lambda s, t: stage.update(s, t, extra=last["text"]))
        run.note(f"{name}: best val {history['best_val']:.4f} "
                 f"({trainer.model.n_params()/1e6:.1f}M params)")


def fine_marginals(run):
    """Empirical distributions for codebooks 5-7, from training audio.

    Measured rather than assumed uniform: 0028 put these stages at 9.49, 9.55
    and 9.55 bits of a possible 10, so they are close to uniform but not
    uniform, and drawing from the real histogram is what 0024's inaudible arm
    actually did.
    """
    with run.stage("marginals") as stage:
        cache = OUT / "fine_marginals.json"
        if cache.exists():
            stage.say("already measured")
            return np.array(json.loads(cache.read_text()))
        from crowgpt.codec import Codec, normalise
        from crowgpt.tokens import BoutStore

        store = BoutStore(BOUTS)
        splits = store.split(seed=0)
        codec = Codec(bandwidth=6.0)
        counts = np.zeros((FULL - KEEP, 1024), dtype=np.int64)
        picks = splits["train"][::max(1, len(splits["train"]) // 300)][:300]
        for n, position in enumerate(picks, 1):
            codes = codec.encode(normalise(store.audio(store.index[position]))).numpy()[0]
            for row in range(KEEP, FULL):
                counts[row - KEEP] += np.bincount(codes[row], minlength=1024)
            stage.update(n, len(picks))
        probs = counts / counts.sum(axis=1, keepdims=True)
        cache.write_text(json.dumps(probs.tolist()))
        del codec
        torch.cuda.empty_cache()
        stage.say(f"{len(picks)} bouts, stages {KEEP}-{FULL - 1}")
        return probs


def generate(run, marginals):
    with run.stage("generate") as stage:
        from crowgpt.codec import Codec, normalise
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
            raise SystemExit(f"only {len(pool)} unused bouts remain")

        rng = np.random.default_rng(0)
        eight = Codec(bandwidth=6.0)
        arms = {"real": [normalise(store.audio(store.index[i])) for i in pool[:PER_ARM]]}
        total = PER_ARM * 4
        stage.update(PER_ARM, total, extra="real")
        done = PER_ARM

        for name, folder in (("k5_matched", MATCHED), ("k5_bigger", BIGGER)):
            sampler = Sampler(folder / "model.pt", token_dir=None)
            made = []
            for i in range(PER_ARM):
                flat = sampler.tokens(SPECIES, temperature=1.0, top_k=200,
                                      seed=3000 + i, max_frames=MAX_FRAMES)
                coarse = sampler.codec.unflatten(flat)
                frames = coarse.shape[1]
                # Stages 5-7 from the measured marginal — the arm 0024 proved
                # inaudible. Decoding five rows instead would be a lower bitrate
                # and would compare a model change against a bandwidth change.
                fine = np.stack([rng.choice(1024, size=frames, p=marginals[r])
                                 for r in range(FULL - KEEP)])
                made.append(eight.decode(torch.from_numpy(
                    np.concatenate([coarse, fine], axis=0)))[0])
                done += 1
                stage.update(done, total, extra=f"{name} {i + 1}/{PER_ARM}")
            arms[name] = made
            del sampler
            torch.cuda.empty_cache()

        sampler = Sampler(CONTROL / "model.pt", token_dir=None)
        made = []
        for i in range(PER_ARM):
            made.append(sampler.audio(SPECIES, temperature=1.0, top_k=200, seed=3000 + i))
            done += 1
            stage.update(done, total, extra=f"fairk8 {i + 1}/{PER_ARM}")
        arms["fairk8"] = made
        del sampler, eight
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
        run.note("units/bout — " + " · ".join(f"{n}={units[n]['mean_units']}" for n in arms))
        return arms


def page(run, arms):
    with run.stage("page") as stage:
        from crowgpt.codec import normalise
        from crowgpt.demo import RatingPage

        clips = [{"audio": normalise(np.asarray(a, dtype=np.float32)), "sr": SR,
                  "arm": name, "n": i}
                 for name, group in arms.items() for i, a in enumerate(group)]
        RatingPage(clips, {
            "Question": "does dropping three inaudible codebooks make the model better",
            "Arms": f"real / k5 matched / k5 bigger / EnCodec-8 incumbent, {PER_ARM} each",
            "Why": "0024 measured codebooks 5-7 inaudible; every run since has "
                   "paid for them. Five codebooks is 62% of the sequence.",
            "Fill": "stages 5-7 drawn from the measured codec marginal, which is "
                    "the arm 0024 proved inaudible — not dropped",
            "Levels": "every clip peak-normalised, real included",
        }, seed=0).write(PAGE)
        (OUT / "clips.json").write_text(json.dumps(
            [{k: v for k, v in c.items() if k != "audio"} for c in clips], indent=2))
        stage.say(str(PAGE))
        run.note(f"page ready: {PAGE}")


def main():
    run = Run("0038 — STOP PAYING FOR INAUDIBLE CODEBOOKS",
              ["tokenize", "k5_matched", "k5_bigger", "marginals", "generate", "page"])
    try:
        tokenize(run)
        for name, folder, shape, micro, accumulate in ARMS:
            train(run, name, folder, shape, micro, accumulate)
        page(run, generate(run, fine_marginals(run)))
        run.note("DONE — rate rate-k5-blind.html")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
