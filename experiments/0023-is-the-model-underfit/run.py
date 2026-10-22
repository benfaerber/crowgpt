"""Is the 18M model underfit, and do the three free knobs move it?

FUTURE.txt has said for a while that every capacity decision here is being made
blind, and it was right. `history.json` recorded `loss.item()` from ONE training
minibatch with dropout 0.25 still active and compared it against a 20-batch mean
under eval(). That is two different measurements, not a gap, which is why
several came out negative — including the call-type run at step 38,000, where
"train" sat above "val". Nothing in results/ can currently say whether this model
is underfit or overfit.

train.py now scores both splits the same way. This sweep uses that to answer the
question and to test the three knobs that cost nothing to change:

  dropout        0.25 on a model that may not be able to fit its own training set
  batch size     a requested 32 is silently clipped to ~14 by a memory budget
                 nobody chose
  lr floor       the cosine settles at 10% of peak and never anneals, so the run
                 ends while still moving

WHAT THE ANSWER LOOKS LIKE. A large positive gap (val well above train) means
overfitting and the dropout is earning its keep. A gap near zero, or negative,
with both losses still falling at the end means underfit — and then capacity or
the objective is the lever, exactly as 0019 argued from the codebook side, and
the three knobs here are the cheap part of that.

Runs are sequential and each writes its own folder, so a night that dies halfway
still leaves the finished ones. Every run is the same length and seed; only the
named knob moves.
"""
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

from crowgpt.progress import Run
from crowgpt.train import Trainer

DATA = Path(__import__("os").environ.get("DATA_DIR") or REPO / "data") / "crowgpt"
TOKENS = DATA / "tokens-calltype"
OUT = HERE / "results" / "sweep-0023"
STEPS = 40_000

ARMS = [
    ("baseline", {}),
    ("dropout-0.10", {"dropout": 0.10}),
    ("dropout-0.00", {"dropout": 0.00}),
    ("batch-32", {"memory_budget": 1_200_000_000}),
    ("anneal-to-zero", {"lr_floor": 0.0}),
    # Added after the first five. Every arm above moved exactly one knob, which
    # is what made them readable, and it also means the two that worked have
    # never been in the same run. Neither is a regulariser the other needs, so
    # there is no reason to expect them to cancel — but "no reason to expect"
    # is why this is measured rather than assumed and folded into the defaults.
    ("batch-32-dropout-0", {"memory_budget": 1_200_000_000, "dropout": 0.00}),
]


def main():
    run = Run("0023 — IS THE MODEL UNDERFIT",
              [name for name, _ in ARMS])
    summary = {}
    OUT.mkdir(parents=True, exist_ok=True)
    for name, knobs in ARMS:
        folder = OUT / name
        if (folder / "history.json").exists():
            run.state[name].update(status="done", note="already on disk, skipped")
            run.write()
            continue
        try:
            with run.stage(name) as stage:
                started = time.time()
                trainer = Trainer(TOKENS, folder, steps=STEPS, n_embd=384, n_layer=8,
                                  n_head=6, seed=0, **knobs)
                stage.say(f"{trainer.model.n_params()/1e6:.1f}M params, "
                          f"batch {trainer.effective_batch}, dropout "
                          f"{trainer.config.dropout}, floor {trainer.lr_floor}")
                history = trainer.run(on_eval=lambda step, val: stage.update(
                    step, STEPS, extra=f"val {val:.4f}"))
                rows = history["history"]
                last = rows[-1]
                summary[name] = {
                    "best_val": history["best_val"],
                    "final_train": last["train"],
                    "final_val": last["val"],
                    "final_gap": last["gap"],
                    "steps_run": last["step"],
                    "batch": trainer.effective_batch,
                    "minutes": round((time.time() - started) / 60, 1),
                }
                run.note(f"{name}: best val {history['best_val']:.4f}, "
                         f"final gap {last['gap']:+.4f} "
                         f"(train {last['train']:.4f} / val {last['val']:.4f})")
                (Path(__file__).resolve().parent / "results.json").write_text(
                    json.dumps(summary, indent=2) + "\n")
        except Exception as exc:
            # One arm failing must not cost the rest of the night.
            run.note(f"{name} FAILED: {type(exc).__name__}: {exc}")
            summary[name] = {"failed": f"{type(exc).__name__}: {exc}"}

    (Path(__file__).resolve().parent / "results.json").write_text(
        json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
