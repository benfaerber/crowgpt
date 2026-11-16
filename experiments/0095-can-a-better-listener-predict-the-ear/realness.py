"""0095: a judge that never sees a grade. A classifier learns real recording
against generated clip on four pools, and on the fifth its "how real" score
for each clip stands in for the ear. Reads the features run.py cached."""
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

from judging import TRAIN_POOLS, Scorer, Trials
from run import ALPHAS, PairJudge, Tournament, WhisperListener

OUT = Path(__file__).resolve().parent


class RealnessJudge:
    name = "realness(whisper-L32)"

    def __init__(self, listener):
        self.listener = listener

    @staticmethod
    def clips(trials):
        labelled = {}
        for t in trials:
            labelled[(t["pool"], t["anchor_clip"])] = 1
            labelled[(t["pool"], t["first_clip"])] = int(t["first_arm"] == "real")
            labelled[(t["pool"], t["second_clip"])] = int(t["second_arm"] == "real")
        return labelled

    def fit(self, trials):
        labelled = self.clips(trials)
        x = np.stack([self.listener.of(*key) for key in labelled])
        self.mean, self.scale = x.mean(0), x.std(0) + 1e-6
        self.model = LogisticRegression(C=0.01, max_iter=2000, class_weight="balanced").fit(
            (x - self.mean) / self.scale, list(labelled.values()))
        return self

    def realness(self, pool, clip):
        x = (self.listener.of(pool, clip) - self.mean) / self.scale
        return float(self.model.decision_function(x[None])[0])

    def predict(self, trials):
        return np.asarray([self.realness(t["pool"], t["first_clip"])
                           - self.realness(t["pool"], t["second_clip"]) for t in trials])


def main():
    trials = Trials()
    graded = {pool: trials.graded(pool) for pool in TRAIN_POOLS}
    everything = {pool: trials.of(pool) for pool in TRAIN_POOLS}
    listener = WhisperListener(32)
    tournament = Tournament(graded)
    graded_judge = PairJudge(listener)
    report = {"realness": {}, "realness+graded": {}}
    for pool in TRAIN_POOLS:
        rest = [p for p in TRAIN_POOLS if p != pool]
        realness = RealnessJudge(listener).fit([t for p in rest for t in everything[p]])
        scores = realness.predict(graded[pool])
        report["realness"][pool] = Scorer.fold(scores, graded[pool])
        graded_judge.fit(tournament.trials(rest), tournament.best_alpha(graded_judge, rest))
        learned = graded_judge.predict(graded[pool])
        both = scores / (scores.std() + 1e-9) + learned / (learned.std() + 1e-9)
        report["realness+graded"][pool] = Scorer.fold(both, graded[pool])
    for folds in report.values():
        rows = list(folds.values())
        folds["mean_spearman"] = round(float(np.mean([f["spearman"] for f in rows])), 3)
        folds["mean_compare_spearman"] = round(float(np.mean([f["compare_spearman"] for f in rows])), 3)
        folds["catch_picks_real"] = round(
            sum(f["catch_picks_real"] * f["catch_n"] for f in rows) / sum(f["catch_n"] for f in rows), 3)
    (OUT / "realness.json").write_text(json.dumps(report, indent=2) + "\n")
    for name, folds in report.items():
        print(name, {k: v for k, v in folds.items() if not isinstance(v, dict)},
              {p: f["spearman"] for p, f in folds.items() if isinstance(f, dict)})


if __name__ == "__main__":
    main()
