"""WP2 arm B: can predicted fine stages stand in for true ones?

The ceiling test for the whole extender architecture, with NO GENERATOR
ANYWHERE. Overnight; `make watch` or the field server's Training panel says
where it is.

WHERE THIS COMES FROM. Five blinded sittings on 2026-08-02 settled the
tokenizer and killed the alternative:

  - DAC 24 kHz at 24 codebooks is indistinguishable from raw and beats EnCodec
    at identical sequence length by 27 points (0033, 0034).
  - That costs 5,400 tokens for a 3-second bout, against the 1,811 the current
    generator handles — and 0030 showed a flat model at 3,619 already fails to
    beat one at 1,811. A flat generator at the transparent bitrate is dead.

So the only route left is coarse-plus-extender: generate 8 codebooks of
structure at ~1,800 tokens, then have a second model fill stages 8-23 before
decoding at 24. This tests the second half of that, and only the second half.

THE QUESTION, PRECISELY. Given the TRUE coarse codes of a real recording, can a
model predict stages 8-23 well enough that the result is as good as decoding the
true stages 8-23? If not, the architecture fails here and no generator is worth
attaching. Nothing in this run generates a bout; every clip starts as a real
held-out recording.

THREE ARMS, DISJOINT BOUTS, BLIND.

    raw            the ceiling, and the anchor every sitting so far has carried
    dac24_true     real bout -> encode 24 cb -> decode. The codec's own ceiling,
                   which 0034 measured at 0.88 against raw's 0.92. THE EXTENDER
                   CANNOT BEAT THIS, so it is the number that matters.
    extender       real bout -> encode 24 cb -> keep the first 8 -> predict
                   8-23 -> decode. The thing being tested.

Read extender-vs-dac24_true, not extender-vs-raw: the codec deficit is already
in both, and charging the extender for it would fail the architecture for
something it does not do.

WHAT WILL LOOK BROKEN AND IS NOT. The coarse stream alone decodes to nothing
listenable — DAC-24 at 12 codebooks scored 0.33 in 0034, the worst arm in the
series, and 8 is fewer still. So any intermediate audio sounds wrong BY DESIGN,
and only the completed 24-codebook decode means anything.

THE GATE THIS DELIBERATELY DOES NOT USE. PLAN-TIMBRE's WP2 gate 1 is "stages
>= 8 beat the codec marginal by > 0.3 bits". 0030 measured 1.46-1.88 bits
recovered in exactly the codebooks 0024 proved INAUDIBLE, so that gate is passed
comfortably by stages nobody can hear and cannot discriminate anything. The
stage profile is still recorded, as description rather than as a gate; the
decision is by ear.
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
TOKENS = DATA / "tokens-dac24"
RESULTS = HERE / "results"
MODEL = RESULTS / "model-extender-dac24"
PAGE = RESULTS / "rate-extender-blind.html"
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
N_CODEBOOKS = 24
FROM_STAGE = 8
STEPS = 20_000
MICRO_BATCH = 3      # 4 fits at 12.3 GiB worst-case but leaves no headroom; 3 peaks at 9.3
ACCUMULATE = 4       # effective 12
BLOCK = 6144         # a 3s bout is 5,427 tokens at 24 cb; the old 4096 cap kept 57%
PER_ARM = 24
MIN_SECONDS = 1.0
# 0028 took the first 260 one-per-recording bouts, then 0033 and 0034 each took
# 120 from the >=1s pool past 380. Start clear of all of them.
SKIP = 380
ALREADY_USED = 240
SR = 24000


def tokenize(run):
    with run.stage("tokenize") as stage:
        if (TOKENS / "manifest.json").exists():
            stage.say("already on disk")
            return
        from crowgpt.dac_codec import DacCodec
        from crowgpt.tokens import BoutStore, TokenWriter

        store = BoutStore(BOUTS)
        splits = store.split(seed=0)
        offsets, running = {}, 0
        for name in splits:
            offsets[name] = running
            running += len(splits[name])
        total = running
        stage.say(f"{len(store)} bouts -> {TOKENS} at DAC-24 {N_CODEBOOKS}cb")
        manifest = TokenWriter(
            store, TOKENS,
            codec=DacCodec(n_codebooks=N_CODEBOOKS, model_type="24khz"),
        ).run(splits, on_progress=lambda split, done, _n: stage.update(
            offsets[split] + done, total, extra=split))
        run.note(f"tokenised {manifest['codec']} K={manifest['n_codebooks']} "
                 f"vocab {manifest['vocab_size']}")


def train(run):
    with run.stage("train") as stage:
        # history.json, not model.pt: the checkpoint is written at every
        # improving eval, so an interrupted run leaves one behind and a resume
        # would accept a 500-step model as finished.
        if (MODEL / "history.json").exists():
            stage.say("already trained")
            return
        from crowgpt.train import Trainer

        trainer = Trainer(
            TOKENS, MODEL,
            steps=STEPS,
            batch_size=MICRO_BATCH,
            accumulate=ACCUMULATE,
            block_size=BLOCK,
            loss_from_stage=FROM_STAGE,
            dropout=0.0,
            n_layer=8, n_head=6, n_embd=384,
            memory_budget=10**10,   # non-binding; MICRO_BATCH is the real limit
            eval_every=500,
        )
        dropped = len(trainer.train_set) - len(trainer.train_batcher.usable)
        if dropped:
            raise SystemExit(
                f"{dropped} sequences exceed the {trainer.config.block_size} block — "
                f"raise BLOCK rather than training on a silently truncated corpus"
            )
        stage.say(f"effective batch {trainer.effective_batch}, "
                  f"block {trainer.config.block_size}, loss from stage {FROM_STAGE}")
        last = {"text": "no eval yet"}

        def note_eval(step, val):
            last["text"] = f"val {val:.4f}"
            stage.update(step, STEPS, extra=last["text"])

        history = trainer.run(
            on_eval=note_eval,
            on_step=lambda step, total: stage.update(step, total, extra=last["text"]),
        )
        run.note(f"extender best val {history['best_val']:.4f} "
                 f"(fine stages only — NOT comparable to any flat run's loss)")


def profile(run):
    """Per-stage bits, as description. Explicitly not the gate — see the header."""
    with run.stage("profile") as stage:
        from crowgpt.model import Config, CrowGPT
        from crowgpt.stages import StageProfile
        from crowgpt.tokens import TokenDataset, Vocabulary

        blob = torch.load(MODEL / "model.pt", map_location="cuda", weights_only=False)
        model = CrowGPT(Config(**blob["config"])).cuda()
        model.load_state_dict(blob["model"])
        manifest = blob["manifest"]
        vocab = Vocabulary(manifest["n_codebooks"], manifest["species"],
                           manifest.get("call_types", ()))
        report = StageProfile(model, vocab, TokenDataset(TOKENS, "val"), device="cuda",
                              batch_size=MICRO_BATCH, batches=8,
                              block_size=BLOCK).measure()
        (OUT / "stage_profile.json").write_text(json.dumps(report, indent=2))
        fine = [r["cross_entropy_bits"] for r in report["stages"] if r["stage"] >= FROM_STAGE]
        stage.say(f"fine-stage CE mean {np.mean(fine):.3f} bits")
        run.note(f"extender fine-stage cross-entropy {np.mean(fine):.3f} bits "
                 f"(description, not a gate)")
        del model
        torch.cuda.empty_cache()


def arm_b(run):
    with run.stage("arm_b") as stage:
        from crowgpt.codec import normalise
        from crowgpt.sample import Sampler
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
        need = PER_ARM * 3
        if len(pool) < need:
            raise SystemExit(f"only {len(pool)} unused bouts remain, need {need}")
        pool = pool[:need]

        sampler = Sampler(MODEL / "model.pt", token_dir=None)
        codec = sampler.codec
        clips, cursor = [], 0
        for arm in ("raw", "dac24_true", "extender"):
            for position in pool[cursor:cursor + PER_ARM]:
                samples = normalise(store.audio(store.index[position]))
                if arm == "raw":
                    audio = samples
                else:
                    codes = codec.encode(samples).numpy()[0]
                    if arm == "extender":
                        flat = sampler.complete_fine(
                            SPECIES, codes[:FROM_STAGE], from_stage=FROM_STAGE,
                            seconds=samples.size / SR, seed=1000 + position)
                        codes = codec.unflatten(flat)
                    audio = codec.decode(torch.from_numpy(codes))[0]
                clips.append({
                    "audio": normalise(np.asarray(audio, dtype=np.float32)),
                    "sr": SR, "arm": arm, "bout": int(position),
                    "recording": store.index[position]["recording_id"],
                    "seconds": round(store.index[position]["n_samples"] / SR, 2),
                })
                stage.update(len(clips), need, extra=arm)
            cursor += PER_ARM
        return clips


def page(run, clips):
    with run.stage("page") as stage:
        from crowgpt.demo import RatingPage

        RatingPage(clips, {
            "Question": "can predicted fine stages stand in for true ones",
            "Arms": f"raw / DAC-24 24cb round-trip / extender-filled, {PER_ARM} bouts each",
            "Read": "extender against the ROUND-TRIP arm, not against raw — "
                    "the codec deficit is in both",
            "Model involved": "an extender only; no bout is generated, every clip "
                              "starts as a real recording",
            "Levels": "every clip peak-normalised after decoding, raw included",
            "Bouts": f">= {MIN_SECONDS}s, disjoint from 0028/0032/0033/0034",
        }, seed=0).write(PAGE)
        (OUT / "clips.json").write_text(json.dumps(
            [{k: v for k, v in c.items() if k != "audio"} for c in clips], indent=2))
        stage.say(str(PAGE))
        run.note(f"morning page: {PAGE}")


def main():
    run = Run("0035 — CAN THE FINE STAGES BE FILLED IN",
              ["tokenize", "train", "profile", "arm_b", "page"])
    try:
        tokenize(run)
        train(run)
        profile(run)
        page(run, arm_b(run))
        run.note("DONE — rate rate-extender-blind.html")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
