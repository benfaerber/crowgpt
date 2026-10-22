"""Is it the data? A scaling curve, which should have come first.

Overnight run for 2026-08-05. `make watch`, or the field server's
Training panel, says where it is.

WHY THIS AND WHY NOW. Five modelling routes have nulled — tokenizer (0028,
0032-0037), capacity twice at two sequence lengths (0023, 0038), sequence length
(0038), the extender architecture (0035), and the token layout (0045). Five
independent ideas, one outcome, which is the signature of a constraint none of
them touched.

The arithmetic nobody ran:

    train corpus         74M unique tokens (148M counting 8x augmentation)
                         41.7 hours across ~2,000 recordings
    model-fair-k8        21.9M params -> Chinchilla wants ~438M tokens
                         so the corpus is 17% of what this model size asks for
    model-k5-bigger      41.0M params -> wants ~820M; the corpus is 9%

For scale, MusicGen trained on 20,000 hours and AudioLM on 60,000. This corpus
is 0.2% of MusicGen's.

A model starved of data by roughly 6x is exactly a model where extra capacity
does not convert (0023, 0038 — both measured it and neither explained it) and
where architecture changes null. It also re-reads 0023's "capacity-starved,
unambiguously", which came off a train/val gap column that has since been found
never to have compared like with like: only the train split is augmented.

WHAT THIS MEASURES. Hold the recipe fixed — d384/L8/H6, effective batch 18,
dropout 0, 30,000 steps, EnCodec 8 codebooks — and vary only how much of the
corpus the model may see. If quality is still climbing steeply at 100%, data is
the binding constraint and no architecture change will help until there is more
of it. If it has flattened, the constraint is something else and this diagnosis
is wrong.

SUBSET BY RECORDING, NEVER BY BOUT. Bouts from one recording are near-duplicates
— it is why the split is grouped at all — so thinning bouts would measure "less
audio per recording" while the decision in front of Ben is "should I go and
collect more recordings". Unlabelled audio buys recordings. The arms are 1,205 /
2,410 / 4,820 / 9,640 recording groups.

THE VALIDATION SPLIT IS NEVER SUBSET. Every arm is scored on the same held-out
data, or the losses are not comparable — a smaller validation set is a different
question, not a smaller answer to the same one.

THE 100% ARM ALREADY EXISTS. `model-fair-k8` is this exact recipe on the whole
corpus, so it is reused rather than retrained, and the run is three arms not
four.

SCORED WITHOUT EARS, deliberately. Validation loss on the shared split, and
0046's stage-0 churn against real audio's 0.868 — the one offline instrument
here that has ever anticipated a listening result (0045) rather than contradicted
it. A sitting can follow if the curve says anything interesting, but the shape of
a scaling curve is not a question the ear answers well.
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
TOKENS = DATA / "tokens"
BOUTS = DATA / "bouts"
RESULTS = HERE / "results"
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
STEPS = 30_000
FRACTIONS = (0.125, 0.25, 0.5)
FULL_ARM = ("1.0", RESULTS / "model-fair-k8")
N_CLIPS = 40
MIN_FRAMES = 40
TARGET_CHURN = 0.868      # real audio's stage-0 churn, measured in 0046


def churn(grids):
    total, seen = np.zeros(8), 0
    for grid in grids:
        if grid.shape[1] < 2:
            continue
        total += (grid[:, 1:] != grid[:, :-1]).mean(axis=1)
        seen += 1
    return total / max(1, seen)


def groups_for(fraction, seed=0):
    from crowgpt.tokens import TokenDataset

    records = TokenDataset(TOKENS, "train").records
    groups = sorted({r["group_key"] for r in records})
    rng = np.random.default_rng(seed)
    keep = set(rng.permutation(groups)[: max(1, int(len(groups) * fraction))])
    tokens = sum(r["length"] for r in records if r["group_key"] in keep)
    return keep, len(keep), tokens


def train_arm(run, fraction):
    name = f"data-{fraction:g}"
    out_dir = RESULTS / f"model-{name}"
    with run.stage(name) as stage:
        keep, n_groups, tokens = groups_for(fraction)
        if (out_dir / "history.json").exists():
            stage.say("already trained")
            return out_dir, n_groups, tokens
        from crowgpt.train import Trainer

        trainer = Trainer(TOKENS, out_dir, steps=STEPS, batch_size=18, accumulate=1,
                          dropout=0.0, n_layer=8, n_head=6, n_embd=384,
                          memory_budget=10**10, eval_every=500, keep_groups=keep)
        if trainer.effective_batch != 18:
            raise SystemExit(f"{name}: effective batch {trainer.effective_batch}")
        stage.say(f"{n_groups} groups · {tokens/1e6:.1f}M tokens · "
                  f"{len(trainer.train_batcher.usable)} sequences")
        last = {"text": "no eval yet"}

        def note_eval(step, val):
            last["text"] = f"val {val:.4f}"
            stage.update(step, STEPS, extra=last["text"])

        history = trainer.run(on_eval=note_eval,
                              on_step=lambda s, t: stage.update(s, t, extra=last["text"]))
        run.note(f"{name}: {n_groups} groups, {tokens/1e6:.0f}M tokens, "
                 f"best val {history['best_val']:.4f}")
    return out_dir, n_groups, tokens


def score(run, arms):
    with run.stage("score") as stage:
        from crowgpt.sample import Sampler

        rows = []
        for n, (label, folder, groups, tokens) in enumerate(arms, 1):
            history = json.loads((folder / "history.json").read_text())
            sampler = Sampler(folder / "model.pt", token_dir=None)
            grids, seed = [], 0
            while len(grids) < N_CLIPS and seed < N_CLIPS * 5:
                grid = sampler.codec.unflatten(sampler.tokens(
                    SPECIES, temperature=1.0, top_k=200, seed=seed))
                seed += 1
                if grid.shape[1] >= MIN_FRAMES:
                    grids.append(grid)
            value = churn(grids)
            rows.append({
                "fraction": label, "groups": groups, "tokens": tokens,
                "best_val": round(history["best_val"], 4),
                "stage0_churn": round(float(value[0]), 4),
                "churn_gap": round(float(value[0] - TARGET_CHURN), 4),
            })
            del sampler
            torch.cuda.empty_cache()
            stage.update(n, len(arms), extra=label)

        (OUT / "results.json").write_text(json.dumps(
            {"target_churn": TARGET_CHURN, "arms": rows}, indent=2))
        for row in rows:
            run.note(f"{row['fraction']}x: {row['tokens']/1e6:.0f}M tokens · "
                     f"val {row['best_val']:.4f} · churn {row['stage0_churn']:.3f}")
        # The shape is the whole point: a curve still falling at 100% means data.
        vals = [r["best_val"] for r in rows]
        if len(vals) >= 2:
            last_step = vals[-2] - vals[-1]
            first_step = vals[0] - vals[1] if len(vals) > 2 else last_step
            run.note(f"val gain from the LAST doubling {last_step:+.4f} "
                     f"against the first {first_step:+.4f} — "
                     f"{'still climbing, data is binding' if last_step > 0.02 else 'flattening'}")
        stage.say("wrote results.json")


def main():
    run = Run("0048 — IS IT THE DATA",
              [f"data-{f:g}" for f in FRACTIONS] + ["score"])
    try:
        arms = []
        for fraction in FRACTIONS:
            folder, groups, tokens = train_arm(run, fraction)
            arms.append((f"{fraction:g}", folder, groups, tokens))
        keep_all, all_groups, all_tokens = groups_for(1.0)
        arms.append((FULL_ARM[0], FULL_ARM[1], all_groups, all_tokens))
        score(run, arms)
        run.note("DONE — read the curve in results.json")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
