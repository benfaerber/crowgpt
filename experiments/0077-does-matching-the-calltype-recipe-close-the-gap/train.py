"""0077's train: the candidate recipe with model-calltype's optimisation.

Via the Trainer API because n_head has no CLI flag (0027's pattern), with the
CLI's own progress wiring reproduced — on_step every update keeps the card
alive well inside the dashboard's stale window.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

from crowgpt.gpu import claim

claim()

from crowgpt.progress import Run
from crowgpt.train import Trainer

TOKENS = REPO / "data" / "crowgpt" / "tokens-6s-ct"
OUT = HERE / "results" / "model-longctx-ct2"
STEPS = 40_000


def main():
    trainer = Trainer(
        TOKENS, OUT, steps=STEPS, n_embd=384, n_layer=8, n_head=6,
        dropout=0.0, batch_size=8, accumulate=4,
    )
    run = Run("TRAIN model-longctx-ct2", ["train"])
    with run.stage("train") as stage:
        stage.update(0, STEPS)
        trainer.run(
            on_step=lambda step, total: stage.update(step, total),
            on_eval=lambda step, val: run.note(f"step {step}: val {val:.4f}"),
        )


if __name__ == "__main__":
    main()
