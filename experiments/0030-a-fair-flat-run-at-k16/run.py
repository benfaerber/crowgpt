"""Does flat-at-12-kbps still lose once the two known bugs are gone?

The unattended overnight job. Start it and go to bed; `make watch` or the
field server's Training panel says where it is.

WHY THIS RUN EXISTS. PLAN-TIMBRE's diagnosis point 4: flat training at 12 kbps
lost badly once, in 0018's ladder — 41.7% detected against 66.7% at 6 kbps — and
that result has been quoted ever since as "higher bandwidth costs more in
sequence length than it returns in ceiling". But 0023 later showed that run
carried two defaults it has since disowned:

  - the batch was silently clipped to about 4 by the memory_budget constant
    (240_000_000 // (3607 x 16420)), not the 32 that was asked for;
  - dropout was 0.25, which 0023 measured as wrong for this corpus.

So a FAIR flat-at-high-bandwidth attempt has never actually run, and a headline
number in the project's reasoning rests on a run nobody would repeat. Even a
failure here is information, which is the whole reason it is worth a night.

IT IS ALSO WP2'S PREREQUISITE, which is why it goes first rather than after the
WP1 listening gate. The extender in WP2 trains on exactly this token stream at
exactly this block size; if a K=16 model cannot be trained well at all on this
hardware, the extender inherits that before it inherits anything else.

WHAT IS HELD CONSTANT, AND THE ONE THING THAT IS NOT. The incumbent
model-d384-6k is d384/L8/H6 at an effective batch of 16. This run matches the
architecture exactly and matches the effective batch through gradient
accumulation (micro-batch 6 x 3), because at K=16 a micro-batch of 8 OOMs on the
4070 Ti and an unaccumulated run would confound bandwidth with batch size. What
is NOT held constant is dropout: the incumbent trained at 0.25 and this runs at
0, deliberately, because that is one of the two bugs being corrected. Read the
result as "fair flat at 12 kbps", not as a clean one-variable contrast with the
incumbent.

WHAT IT DECIDES. Nothing on its own — the gates in PLAN-TIMBRE are by ear, and
this writes a page for the morning rather than a verdict. What it produces is
the per-stage bits profile (does the model beat the codec marginal in stages
8-15 at all, which is the number WP2 lives or dies on) and a blinded rating page
against the incumbent and against real audio.

SAFE TO INTERRUPT. Every stage checks for its own output first, so re-running
resumes. Nothing here writes to results/model, which is what the published demo
plays.
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

from crowgpt.progress import Run

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
BOUTS = DATA / "bouts"
TOKENS = DATA / "tokens-k16"
TOKENS_K8 = DATA / "tokens"
RESULTS = HERE / "results"
MODEL = RESULTS / "model-flat-k16"
CONTROL = RESULTS / "model-fair-k8"
PAGE = RESULTS / "rate-flat-k16.html"
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
# 30,000 STEPS SO EARLY STOPPING GOVERNS, NOT THE CLOCK. 0023 saw the best model
# reach its lowest validation loss at step 19,000, so a budget below that
# measures the budget. Patience is 8,000 stale steps, which now decides where
# each arm stops.
#
# A synthetic benchmark at the full 3,619-token block said 1.11 s a step and
# would have forced a much smaller number. It was wrong, and usefully so:
# `Batcher` pads to the longest sequence IN THE BATCH rather than to block_size,
# and the median bout is about a third of the block, so real steps are roughly
# three times cheaper. Measured on the live run instead — about 0.36 s a step at
# K=16, which puts the pair at roughly 4 h.
#
# BOTH ARMS GET THE SAME COUNT. That is what makes bandwidth the only difference.
STEPS = 30_000
# THE CONTROL ARM IS NOT OPTIONAL, and 0027 is why: it closed owing "a same-size
# control before this is quoted as 'filtering does not work' rather than
# 'filtering at 45% of the data does not work'". The same trap is set here. The
# incumbent model-d384-6k trained at dropout 0.25 and effective batch 16, and
# this run is dropout 0 at effective batch 18 — so flat-K16 against the
# incumbent would compare bandwidth AND dropout AND batch in one number, and any
# difference could be credited to the wrong one. model-fair-k8 is the identical
# recipe at eight codebooks, which makes bandwidth the only thing that moves.
EFFECTIVE_BATCH = 18
MICRO_BATCH = 6      # 8 OOMs at d384/L8/K16 on a 16 GB card; measured, not guessed
ACCUMULATE = 3
MICRO_BATCH_K8 = 18  # a quarter of the logits tensor at K=8, so it fits outright
ACCUMULATE_K8 = 1
N_RATE_PER_ARM = 20

# 0028 measured these on 200 held-out bouts, one per recording, at 24 kbps.
# NOT reused from stages.CODEC_MARGINAL_BITS, which is 0014's eight-stage table
# measured on BirdNET-gated windows — a denser, more stereotyped sample that
# reads about 1.5 bits lower. 0017 already documented that those two samples
# disagree about the codec and that only one of them is a statement about it.
# Swapping the shared constant would silently move every StageProfile number
# 0019, 0023 and 0027 ever reported.
CODEC_MARGINAL_K16 = [7.57, 8.37, 8.86, 9.19, 9.39, 9.49, 9.55, 9.55,
                      9.63, 9.58, 9.58, 9.56, 9.50, 9.47, 9.43, 9.38]


def tokenize(run):
    with run.stage("tokenize") as stage:
        if (TOKENS / "manifest.json").exists():
            stage.say("already on disk")
            return
        from crowgpt.tokens import BoutStore, TokenWriter

        store = BoutStore(BOUTS)
        splits = store.split(seed=0)
        stage.say(f"{len(store)} bouts -> {TOKENS}")

        # One bar across all three splits rather than three that each restart at
        # zero: the dashboard shows a fraction, and a fraction that resets twice
        # reads as a stall.
        order = list(splits)
        offsets, running = {}, 0
        for name in order:
            offsets[name] = running
            running += len(splits[name])
        total = running

        manifest = TokenWriter(store, TOKENS, bandwidth=12.0).run(
            splits,
            on_progress=lambda split, done, _n: stage.update(
                offsets[split] + done, total, extra=split
            ),
        )
        stage.say(f"K={manifest['n_codebooks']} vocab {manifest['vocab_size']}")
        run.note(f"tokenised at 12 kbps: K={manifest['n_codebooks']}, "
                 f"{manifest['splits']['train']['sequences']} train sequences")


def train(run, name, token_dir, out_dir, micro, accumulate):
    with run.stage(name) as stage:
        # history.json, NOT model.pt. The checkpoint is written at every eval
        # that improves, so an interrupted arm leaves one behind after 500 steps
        # and a resume would silently accept it as a finished run — a 500-step
        # model quietly standing in for a 30,000-step one, in a comparison whose
        # whole point is that the two arms got identical treatment. history.json
        # is written once, after the loop exits.
        if (out_dir / "history.json").exists():
            stage.say("already trained")
            return
        from crowgpt.train import Trainer

        trainer = Trainer(
            token_dir, out_dir,
            steps=STEPS,
            batch_size=micro,
            accumulate=accumulate,
            dropout=0.0,
            n_layer=8, n_head=6, n_embd=384,
            memory_budget=10**9,     # non-binding; the micro-batch is the real limit
            eval_every=500,
        )
        if trainer.effective_batch != EFFECTIVE_BATCH:
            # The whole point of the control is that one number differs. If the
            # memory_budget heuristic clipped either arm, it did not.
            raise SystemExit(
                f"{name}: effective batch {trainer.effective_batch}, "
                f"expected {EFFECTIVE_BATCH} — the arms are no longer comparable"
            )
        stage.say(f"effective batch {trainer.effective_batch}, block {trainer.config.block_size}")
        last_val = {"text": "no eval yet"}

        def note_eval(step, val):
            last_val["text"] = f"val {val:.4f}"
            stage.update(step, STEPS, extra=last_val["text"])

        history = trainer.run(
            on_eval=note_eval,
            on_step=lambda step, total: stage.update(step, total, extra=last_val["text"]),
        )
        run.note(f"{name}: best val {history['best_val']:.4f}, "
                 f"effective batch {trainer.effective_batch}, dropout 0")


def profile(run):
    """Per-stage bits. The number WP2 lives or dies on is stages 8-15.

    VALIDATION LOSS IS NOT COMPARED ACROSS THE TWO ARMS anywhere here, and must
    not be: K=8 and K=16 have different vocabularies and different sequence
    lengths, so their cross-entropies are different quantities that happen to
    share a unit. Bits recovered against each stage's own codec marginal is the
    comparable thing, and even that is only read per stage.
    """
    with run.stage("profile") as stage:
        import torch

        from crowgpt.model import Config, CrowGPT
        from crowgpt.stages import StageProfile
        from crowgpt.tokens import TokenDataset, Vocabulary

        reports = {}
        arms = [("flat_k16", MODEL, TOKENS, MICRO_BATCH),
                ("fair_k8", CONTROL, TOKENS_K8, MICRO_BATCH_K8)]
        for n, (name, folder, token_dir, batch) in enumerate(arms, 1):
            blob = torch.load(folder / "model.pt", map_location="cuda", weights_only=False)
            model = CrowGPT(Config(**blob["config"])).cuda()
            model.load_state_dict(blob["model"])
            manifest = blob["manifest"]
            vocab = Vocabulary(manifest["n_codebooks"], manifest["species"],
                               manifest.get("call_types", ()))
            report = StageProfile(model, vocab, TokenDataset(token_dir, "val"), device="cuda",
                                  batch_size=batch, batches=12).measure()

            # Recompute bits_recovered against the marginal measured on THIS
            # corpus: StageProfile's table stops at stage 7 and reports nan past
            # it, and its numbers come from a different sample (see the constant).
            for row in report["stages"]:
                marginal = CODEC_MARGINAL_K16[row["stage"]]
                row["marginal_bits_0028"] = marginal
                row["bits_recovered_0028"] = round(marginal - row["cross_entropy_bits"], 4)

            coarse = [r["bits_recovered_0028"] for r in report["stages"] if r["stage"] < 8]
            fine = [r["bits_recovered_0028"] for r in report["stages"] if r["stage"] >= 8]
            report["coarse_bits_recovered"] = round(float(np.mean(coarse)), 3) if coarse else None
            report["fine_bits_recovered"] = round(float(np.mean(fine)), 3) if fine else None
            reports[name] = report
            del model
            torch.cuda.empty_cache()
            stage.update(n, len(arms), extra=name)

        (OUT / "stage_profile.json").write_text(json.dumps(reports, indent=2))

        fine = reports["flat_k16"]["fine_bits_recovered"]
        verdict = ("fine stages beat the codec marginal — WP2 has something to model"
                   if (fine or 0) > 0.3 else
                   "fine stages do NOT clear 0.3 bits over the marginal — WP2's gate 1 fails here")
        stage.say(f"k16 coarse {reports['flat_k16']['coarse_bits_recovered']} · "
                  f"fine {fine} bits")
        run.note(f"stage profile k16: coarse +{reports['flat_k16']['coarse_bits_recovered']} bits, "
                 f"fine +{fine} bits — {verdict}")
        run.note(f"stage profile k8 control: coarse "
                 f"+{reports['fair_k8']['coarse_bits_recovered']} bits")


def _units(clips, segmenter):
    counts = []
    for samples in clips:
        _, units = segmenter.segment(np.asarray(samples, dtype=np.float32), 24000)
        counts.append(len(units))
    return counts


def generate(run):
    """Three arms of audio for the morning, plus units-per-bout on each."""
    with run.stage("generate") as stage:
        import torch

        from crowgpt.codec import normalise
        from crowgpt.sample import Sampler
        from crowgpt.segment import Segmenter
        from crowgpt.tokens import BoutStore

        arms = {}

        store = BoutStore(BOUTS)
        splits = store.split(seed=0)
        held = [i for i in splits["test"] if store.index[i]["species"] == SPECIES]
        seen, chosen = set(), []
        for i in held:
            if store.index[i]["recording_id"] in seen:
                continue
            seen.add(store.index[i]["recording_id"])
            chosen.append(i)
            if len(chosen) >= N_RATE_PER_ARM:
                break
        arms["real"] = [normalise(store.audio(store.index[i])) for i in chosen]
        stage.update(1, 3, extra="real")

        # PER CLIP, NOT PER ARM. Sampling is autoregressive over 225 frames x 16
        # codebooks, so one clip is tens of seconds and an arm is ten minutes or
        # more. The dashboard flags a run stale after 600 s without a write
        # (fieldserver/api/training.py), so updating once per arm would show a
        # live run as hung for exactly the stretch it is working hardest.
        total = 1 + 2 * N_RATE_PER_ARM
        done = 1
        for name, folder in (("flat_k16", MODEL), ("fair_k8", CONTROL)):
            sampler = Sampler(folder / "model.pt", token_dir=None)
            made = []
            for i in range(N_RATE_PER_ARM):
                made.append(sampler.audio(SPECIES, temperature=1.0, top_k=200, seed=1000 + i))
                done += 1
                stage.update(done, total, extra=f"{name} {i + 1}/{N_RATE_PER_ARM}")
            arms[name] = made
            del sampler
            torch.cuda.empty_cache()

        segmenter = Segmenter()
        units = {name: _units(clips, segmenter) for name, clips in arms.items()}
        report = {
            name: {
                "clips": len(values),
                "mean_units": round(float(np.mean(values)), 2),
                "single_unit_share": round(float((np.array(values) <= 1).mean()), 3),
                "histogram": {str(k): v for k, v in sorted(Counter(values).items())},
            }
            for name, values in units.items()
        }
        (OUT / "units.json").write_text(json.dumps(report, indent=2))
        run.note("units/bout — " + " · ".join(
            f"{n}={report[n]['mean_units']}" for n in ("real", "flat_k16", "fair_k8")))
        return arms


def page(run, arms):
    with run.stage("page") as stage:
        from crowgpt.demo import RatingPage

        clips = [
            {"audio": samples, "sr": 24000, "arm": name, "n": i}
            for name, group in arms.items()
            for i, samples in enumerate(group)
        ]
        RatingPage(clips, {
            "Question": "at an identical recipe, does 12 kbps sound better than 6?",
            "Arms": f"real / flat-k16 / fair-k8, {N_RATE_PER_ARM} each",
            "Training": f"both models d384 L8 H6, effective batch {EFFECTIVE_BATCH}, "
                        f"dropout 0, {STEPS} steps — bandwidth is the only difference",
            "Power": "resolves a ~20-point difference between arms, not a 10-point one",
        }, seed=0).write(PAGE)
        stage.say(str(PAGE))
        run.note(f"morning page: {PAGE}")


def main():
    run = Run("0030 — A FAIR FLAT RUN AT K=16",
              ["tokenize", "train_k16", "train_k8", "profile", "generate", "page"])
    try:
        tokenize(run)
        train(run, "train_k16", TOKENS, MODEL, MICRO_BATCH, ACCUMULATE)
        train(run, "train_k8", TOKENS_K8, CONTROL, MICRO_BATCH_K8, ACCUMULATE_K8)
        profile(run)
        arms = generate(run)
        page(run, arms)
        run.note("DONE — rate the pages in the morning")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
