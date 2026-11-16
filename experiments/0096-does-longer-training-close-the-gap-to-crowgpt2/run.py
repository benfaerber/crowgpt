"""0096: 0086's larger model on a 60k schedule, at 0086's best rate and at twice it.

Reuses 0086's controlled trainer and its full-validation score, so the
numbers sit beside 0086's table. Re-running resumes a stopped arm. No
listening pool is built: the answer is the validation loss.
"""
import gc
import hashlib
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "crowgpt/src"))
sys.path.insert(0, str(REPO / "experiments/0086-can-tuned-training-improve-crowgpt2"))

import torch

from crowgpt.model import Config, CrowGPT, LegalMask
from crowgpt.progress import Run
from crowgpt.tokens import TokenDataset, Vocabulary
from crowgpt.train import require_device
from training import ControlledTrainer, atomic_json, score

DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
TOKENS = DATA / "crowgpt/tokens-6s"
OUTPUT = REPO / "crowgpt/results/longer-0096"
ARMS = {"60k-lr-3e-4": 3e-4, "60k-lr-6e-4": 6e-4}
RECIPE = dict(steps=60000, batch_size=8, accumulate=1, n_embd=512, n_layer=12,
              n_head=4, dropout=0.0, seed=0, warmup=200, eval_every=1000,
              panel_size=256, checkpoint_every=10000)
REFERENCES = {
    "CrowGPT2": REPO / "crowgpt/results/model-longctx/model.pt",
    "0086 selected (30k, lr 3e-4)": REPO / "crowgpt/results/tuning-0086/selected/model.pt",
}


class FullValidation:
    """0086's selection metric: token-weighted cross entropy over every
    canonical American Crow validation bout."""

    def __init__(self):
        self.dataset = TokenDataset(TOKENS, "val")
        self.indices = [i for i, r in enumerate(self.dataset.records)
                        if r["species"] == "american-crow" and r.get("canonical", True)]

    def of(self, path, on_progress=None):
        state = torch.load(path, map_location="cpu", weights_only=False)
        config = Config(**state["config"])
        model = CrowGPT(config).to("cuda")
        model.load_state_dict(state["model"])
        manifest = state["manifest"]
        vocabulary = Vocabulary(manifest["n_codebooks"], manifest["species"],
                                n_unit_buckets=manifest.get("n_unit_buckets", 0))
        legal = LegalMask(vocabulary, config.block_size + 1, "cuda")
        loss = score(model, legal, self.dataset, self.indices, "cuda", batch_size=8,
                     on_progress=on_progress)
        row = {"path": str(path.relative_to(REPO)), "step": state["step"], "full_ac_val": loss,
               "checkpoint_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        del model, state, legal
        gc.collect()
        torch.cuda.empty_cache()
        return row


def main():
    if require_device() != "cuda":
        raise RuntimeError("0096 needs the GPU")
    run = Run("0096 longer training for the larger CrowGPT", [*ARMS, "full validation"])
    failures = {}
    for name, rate in ARMS.items():
        with run.stage(name) as stage:
            trainer = ControlledTrainer(TOKENS, OUTPUT / name, learning_rate=rate, **RECIPE)
            try:
                result = trainer.run(
                    on_step=lambda done, total: stage.update(done, total),
                    on_eval=lambda step, val: run.note(f"{name} step {step}: panel val {val:.4f}"))
                stage.say(f"60k schedule complete; best panel val {result['best_val']:.4f}")
            except RuntimeError as error:
                failures[name] = str(error)
                stage.say(f"stopped: {error}")
            del trainer
            gc.collect()
            torch.cuda.empty_cache()

    with run.stage("full validation") as stage:
        validation = FullValidation()
        paths = {label: path for label, path in REFERENCES.items()}
        for name in ARMS:
            for path in sorted((OUTPUT / name).glob("step-*.pt")):
                paths[f"{name} {path.stem}"] = path
        rows = []
        for n, (label, path) in enumerate(paths.items()):
            row = validation.of(path, on_progress=lambda done, total: stage.update(
                n * len(validation.indices) + done, len(paths) * len(validation.indices), extra=label))
            rows.append(dict(row, label=label))
            print(rows[-1], flush=True)
            atomic_json(HERE / "results.json", {
                "validation_bouts": len(validation.indices), "recipe": RECIPE, "rates": ARMS,
                "failures": failures, "checkpoints": rows})


if __name__ == "__main__":
    main()
