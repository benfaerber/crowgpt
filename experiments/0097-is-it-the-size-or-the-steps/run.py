"""0097: CrowGPT2's own size on 0096's 60k schedule, the control 0096 lacked.

0096's larger model passed CrowGPT2 once it trained for 60,000 steps, but
CrowGPT2 only ever had 30,000. Same trainer, panels, seed, batch order,
rates and full-validation score as 0096; only the model is smaller.
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

OUTPUT = REPO / "crowgpt/results/control-0097"
RECIPE = dict(longer.RECIPE, n_embd=384, n_layer=8, n_head=4)
REFERENCES = dict(longer.REFERENCES)
REFERENCES["0096 larger model, 60k, lr 6e-4"] = longer.OUTPUT / "60k-lr-6e-4/step-60000.pt"
REFERENCES["0096 larger model, 60k, lr 3e-4"] = longer.OUTPUT / "60k-lr-3e-4/step-60000.pt"

if __name__ == "__main__":
    longer.LongSchedule("0097 CrowGPT2's size on the 60k schedule", OUTPUT, longer.ARMS, RECIPE,
                        HERE / "results.json", REFERENCES).main()
