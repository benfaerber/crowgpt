"""Does training on 46 corvid species help American Crow, or dilute it?

Overnight run for 2026-08-05. `make watch` or the field server's Training
panel.

THE QUESTION BEN ASKED, IN HIS OWN FRAME: "is it trained on all languages or
just english?" The corpus is now 46 species where it was 6, because the sweep
brought back 10,637 recordings of which only 446 were American Crow. So the
model can be trained monolingually or multilingually and the difference is
finally measurable.

WHY IT IS NOT OBVIOUS EITHER WAY. Multilingual language models show a "curse of
multilinguality" — adding languages hurts the high-resource one — but only when
CAPACITY is the binding constraint, because languages then compete for
parameters. When DATA binds, transfer runs the other way and every language
helps the others. 0048 could not settle which regime this is: it found data
saturated at 22M parameters, which is the capacity-bound signature, while 0023
and 0038 found capacity not converting, which is not.

The model already carries a species token in its prefix, so this is mT5's
design rather than an averaged voice: it is told which species to produce.

TWO ARMS, ONE DIFFERENCE.

    mono    trains on american-crow only          100,216 sequences
    multi   trains on all 46 species              214,090 sequences

Same tokens directory, so the VOCABULARY IS IDENTICAL (8,247, 46 species tokens)
and the model shape does not move. The mono arm simply never sees the other
species in training. Anything else would confound the data question with an
embedding-size question.

BOTH ARE SCORED ON THE SAME HELD-OUT AMERICAN CROW — 4,560 sequences, filtered
identically. This is the part that would silently break the experiment: the
multi arm's unfiltered validation loss is an average over 46 species and would
move for reasons having nothing to do with American Crow.

THE UPSAMPLE STAYS ON for the multi arm. `AMERICAN_CROW_UPSAMPLE = 3.0` is what
a deployed multilingual model would use — target-language upsampling is standard
— and turning it off would hand the mono arm a win by starving multi of the
species being scored. Note the mix has shifted underneath it though: American
Crow was 71% of the old corpus and is 47% of this one, so the same 3.0 buys less
than it used to.

WHAT IT CANNOT SETTLE. Fixed steps means the mono arm does roughly twice the
epochs over half the data, so it has more opportunity to overfit. That is the
honest form of the question — "given the same compute, which corpus is better to
train on" — but it is not the same as "which is better given unlimited compute".
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
TOKENS = DATA / "tokens-v2"
BOUTS = DATA / "bouts"
RESULTS = HERE / "results"
PAGE = RESULTS / "rate-multilingual-blind.html"
OUT = Path(__file__).resolve().parent

SPECIES = "american-crow"
CROW = {SPECIES}
STEPS = 30_000
ARMS = (("mono", CROW), ("multi", None))
N_PAIRS, N_CATCH = 50, 10
MIN_SECONDS = 1.0
N_CHURN = 40
TARGET_CHURN = 0.868      # real audio's stage-0 churn (0046)


def churn(grids):
    total, seen = np.zeros(8), 0
    for grid in grids:
        if grid.shape[1] < 2:
            continue
        total += (grid[:, 1:] != grid[:, :-1]).mean(axis=1)
        seen += 1
    return total / max(1, seen)


def train_arm(run, name, keep):
    out_dir = RESULTS / f"model-{name}-v2"
    with run.stage(name) as stage:
        if (out_dir / "history.json").exists():
            stage.say("already trained")
            return out_dir
        from crowgpt.train import Trainer

        trainer = Trainer(TOKENS, out_dir, steps=STEPS, batch_size=18, accumulate=1,
                          dropout=0.0, n_layer=8, n_head=6, n_embd=384,
                          memory_budget=10**10, eval_every=500,
                          keep_species=keep, eval_species=CROW)
        if trainer.effective_batch != 18:
            raise SystemExit(f"{name}: effective batch {trainer.effective_batch}")
        stage.say(f"{len(trainer.train_batcher.usable):,} train seqs · "
                  f"{len(trainer.val_batcher.usable):,} val seqs (crow only)")
        last = {"text": "no eval yet"}

        def note_eval(step, val):
            last["text"] = f"val {val:.4f}"
            stage.update(step, STEPS, extra=last["text"])

        history = trainer.run(on_eval=note_eval,
                              on_step=lambda s, t: stage.update(s, t, extra=last["text"]))
        run.note(f"{name}: {len(trainer.train_batcher.usable):,} train seqs, "
                 f"best val {history['best_val']:.4f} (on held-out American Crow)")
    return out_dir


def sample_arm(sampler, count, first_seed, on_clip):
    from crowgpt.codec import normalise

    kept, seed = [], 0
    while len(kept) < count and seed < count * 8:
        audio = sampler.audio(SPECIES, temperature=1.0, top_k=200,
                              seed=first_seed + seed)
        seed += 1
        if len(audio) / 24000 >= MIN_SECONDS:
            kept.append(normalise(np.asarray(audio, dtype=np.float32)))
            on_clip()
    return kept


def evaluate(run, arms):
    with run.stage("evaluate") as stage:
        from crowgpt.codec import normalise
        from crowgpt.sample import Sampler
        from crowgpt.tokens import BoutStore

        made, scores, done = {}, {}, 0
        total = N_PAIRS * 2 + N_CATCH

        def tick():
            nonlocal done
            done += 1
            stage.update(done, total)

        for name, folder in arms:
            sampler = Sampler(folder / "model.pt", token_dir=None)
            made[name] = sample_arm(sampler, N_PAIRS, 11000, tick)
            grids, seed = [], 0
            while len(grids) < N_CHURN and seed < N_CHURN * 5:
                grid = sampler.codec.unflatten(sampler.tokens(
                    SPECIES, temperature=1.0, top_k=200, seed=20000 + seed))
                seed += 1
                if grid.shape[1] >= 40:
                    grids.append(grid)
            value = churn(grids)
            history = json.loads((folder / "history.json").read_text())
            scores[name] = {"best_val": round(history["best_val"], 4),
                            "stage0_churn": round(float(value[0]), 4),
                            "churn_gap": round(float(value[0] - TARGET_CHURN), 4)}
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
        pool = [i for i in ordered if store.index[i]["n_samples"] / 24000 >= MIN_SECONDS]
        made["real"] = [normalise(store.audio(store.index[i])) for i in pool[:N_CATCH]]
        done += N_CATCH
        stage.update(done, total, extra="real")

        (OUT / "scores.json").write_text(json.dumps(scores, indent=2))
        for name, row in scores.items():
            run.note(f"{name}: val {row['best_val']:.4f} · churn {row['stage0_churn']:.3f} "
                     f"({row['churn_gap']:+.3f} vs real)")
        return made


def page(run, made):
    with run.stage("page") as stage:
        from crowgpt.demo import PairPage

        def clip(name, i):
            return {"audio": made[name][i], "sr": 24000, "arm": name}

        pairs = [{"a": clip("multi", i), "b": clip("mono", i)} for i in range(N_PAIRS)]
        pairs += [{"a": clip("real", i), "b": clip("mono", N_PAIRS - 1 - i),
                   "catch": True} for i in range(N_CATCH)]
        PairPage(pairs, {
            "Question": "does training on 46 species help American Crow, or dilute it",
            "Pairs": f"{N_PAIRS} multi vs mono · {N_CATCH} real vs mono (catch)",
            "One difference": "identical recipe and identical vocabulary; mono sees "
                              "only american-crow in training, multi sees all 46",
            "Scored on": "held-out American Crow for both arms",
            "Clips": f"all >= {MIN_SECONDS}s; sides and play order balanced 2x2",
        }, seed=0).write(PAGE)
        stage.say(str(PAGE))
        run.note(f"{len(pairs)} pairs -> {PAGE}")


def main():
    run = Run("0049 — 46 SPECIES OR ONE",
              ["mono", "multi", "evaluate", "page"])
    try:
        trained = [(name, train_arm(run, name, keep)) for name, keep in ARMS]
        page(run, evaluate(run, trained))
        run.note("DONE — rate rate-multilingual-blind.html")
    except Exception as exc:
        run.note(f"FAILED: {type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
