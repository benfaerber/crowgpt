"""0095: does the judge keep improving as it is given more graded sittings?

For each held-out pool, the Whisper judge is fitted on every subset of the
other four and scored. Reads the features run.py cached; no model is loaded.
"""
import json
from itertools import combinations
from pathlib import Path

import numpy as np

from judging import TRAIN_POOLS, Scorer, Trials
from run import PairJudge, WhisperListener

OUT = Path(__file__).resolve().parent
ALPHA = 1000.0


def main():
    trials = Trials()
    graded = {pool: trials.graded(pool) for pool in TRAIN_POOLS}
    judge = PairJudge(WhisperListener(32))
    by_size = {}
    for held in TRAIN_POOLS:
        rest = [pool for pool in TRAIN_POOLS if pool != held]
        grades = [t["grade"] for t in graded[held]]
        for size in range(1, len(rest) + 1):
            for subset in combinations(rest, size):
                train = [t for pool in subset for t in graded[pool]]
                judge.fit(train, ALPHA)
                by_size.setdefault(size, []).append(
                    {"answers": len(train),
                     "spearman": Scorer.spearman(judge.predict(graded[held]), grades)})
    report = {str(size): {"fits": len(rows),
                          "mean_answers": round(float(np.mean([r["answers"] for r in rows]))),
                          "mean_spearman": round(float(np.mean([r["spearman"] for r in rows])), 3)}
              for size, rows in by_size.items()}
    (OUT / "curve.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
