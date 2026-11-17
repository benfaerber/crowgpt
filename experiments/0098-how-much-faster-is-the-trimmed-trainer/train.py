"""0098, second half: does the faster trainer reach the same loss?

0097's best arm (CrowGPT2's size, 60k steps, peak rate 0.0006) again with
the sliced loss and length-bucketed batches, scored beside the original.
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LONGER = REPO / "experiments/0096-does-longer-training-close-the-gap-to-crowgpt2"

spec = importlib.util.spec_from_file_location("longer_0096", LONGER / "run.py")
longer = importlib.util.module_from_spec(spec)
sys.modules["longer_0096"] = longer
spec.loader.exec_module(longer)

OUTPUT = REPO / "crowgpt/results/trimmed-0098"
RECIPE = dict(longer.RECIPE, n_embd=384, n_layer=8, n_head=4, sliced_loss=True, bucketed=True)
REFERENCES = {
    "CrowGPT2": longer.REFERENCES["CrowGPT2"],
    "0097 same arm, plain trainer": REPO / "crowgpt/results/control-0097/60k-lr-6e-4/step-60000.pt",
}

if __name__ == "__main__":
    longer.LongSchedule("0098 the faster trainer, full schedule", OUTPUT, {"trimmed-lr-6e-4": 6e-4},
                        RECIPE, HERE / "train_results.json", REFERENCES).main()
