"""EXPLORATORY — is the guard failure at seed 0 a property of the additions or of the seed?

Not part of the pre-registered protocol, which scores the guard at seed 0 only
and whose verdict stands whatever this prints. Run after `run.py`.

    pipelines/representation/.venv-birdnet/bin/python \
        experiments/0108-do-witnessed-begging-clips-help/guard_seeds.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import run as exp
from crowgpt.progress import Run

HERE = Path(__file__).resolve().parent
SEEDS = list(range(10))


class GuardSpread:
    def __init__(self):
        self.protocol = exp.Protocol(exp.EvalSet(), exp.Additions())

    def measure(self, stage):
        plan = [(c, s) for c in exp.GUARD_CLASSES for s in SEEDS]
        scores = self.protocol.run(plan, stage)
        out = {}
        for rule in exp.RULES:
            out[rule] = {}
            for cls in exp.GUARD_CLASSES:
                drops = [scores[(cls, s)]["baseline"]["auc"] - scores[(cls, s)][rule]["auc"]
                         for s in SEEDS]
                out[rule][cls] = {"mean_drop": round(float(np.mean(drops)), 4),
                                  "min": round(min(drops), 4), "max": round(max(drops), 4),
                                  "seeds_with_a_drop": int(sum(d > 0 for d in drops))}
        return out


def main():
    run = Run("0108 guard spread (exploratory)", ["guard_seeds"])
    with run.stage("guard_seeds") as stage:
        report = GuardSpread().measure(stage)
    (HERE / "guard_seeds.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
