"""0098: what the sliced loss and length-bucketed batches buy, in real tokens per second.

Times the larger model (d512/L12/H4) for a fixed number of optimiser steps
in each configuration, after a warm-up. The useful rate is non-padding
target tokens per second, since a padded position teaches nothing.
"""
import gc
import json
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "crowgpt/src"))

import torch

from crowgpt.progress import Run
from crowgpt.train import Trainer

TOKENS = REPO / "data/crowgpt/tokens-6s"
MODEL = dict(n_embd=512, n_layer=12, n_head=4, dropout=0.0, seed=0)
ARMS = {
    "as trained in 0096": dict(batch_size=8),
    "sliced loss": dict(batch_size=8, sliced_loss=True),
    "bucketed": dict(batch_size=8, bucketed=True),
    "sliced + bucketed": dict(batch_size=8, sliced_loss=True, bucketed=True),
    "sliced + bucketed, batch 16": dict(batch_size=16, sliced_loss=True, bucketed=True),
    "sliced + bucketed, batch 32": dict(batch_size=32, sliced_loss=True, bucketed=True),
}
WARMUP, STEPS = 20, 200


class Stopwatch:
    def __init__(self, options):
        self.trainer = Trainer(TOKENS, tempfile.mkdtemp(), memory_budget=10**12, **MODEL, **options)
        self.optimizer = self.trainer.model.optimiser(3e-4)

    def step(self):
        x, y = self.trainer.train_batcher.batch()
        self.optimizer.zero_grad(set_to_none=True)
        loss = self.trainer._loss(x, y)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.trainer.model.parameters(), 1.0)
        self.optimizer.step()
        return int((y != -1).sum()), y.numel(), float(loss)

    def measure(self, on_step):
        for _ in range(WARMUP):
            self.step()
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        real = padded = 0
        started = time.monotonic()
        for n in range(STEPS):
            tokens, cells, loss = self.step()
            real, padded = real + tokens, padded + cells
            on_step(n + 1)
        torch.cuda.synchronize()
        seconds = time.monotonic() - started
        return {"batch": self.trainer.micro_batch, "seconds_per_step": seconds / STEPS,
                "sequences_per_second": self.trainer.micro_batch * STEPS / seconds,
                "real_tokens_per_second": real / seconds, "real_share_of_batch": real / padded,
                "peak_gib": torch.cuda.max_memory_allocated() / 2**30, "last_loss": loss}


def main():
    run = Run("0098 trainer speed", list(ARMS))
    results = {}
    for name, options in ARMS.items():
        with run.stage(name) as stage:
            try:
                results[name] = Stopwatch(options).measure(lambda n: stage.update(n, STEPS))
            except torch.OutOfMemoryError:
                results[name] = {"failed": "out of memory"}
            print(name, json.dumps(results[name]), flush=True)
            gc.collect()
            torch.cuda.empty_cache()
            (HERE / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
