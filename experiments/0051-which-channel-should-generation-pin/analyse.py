"""What predicts a bucket's churn, and is any bucket on target?

Run after `run.py`. Reads results.json and asks the question the sweep raises
rather than the one it was designed for: the first two arms differed by 0.199,
which is larger than anything 0047's sampling sweep reached without mangling the
distribution, so the interesting quantity is what the spread tracks.

Spearman rather than Pearson: with 13 arms the shape of the relationship is not
worth assuming, and one bucket with 448 recordings would dominate any fit on raw
values.
"""
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent
TARGET = 0.868


def spearman(x, y):
    """Rank correlation and a permutation p, so n=13 is not handed to a t-table."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    rx, ry = x.argsort().argsort(), y.argsort().argsort()
    rho = np.corrcoef(rx, ry)[0, 1]
    rng = np.random.default_rng(0)
    null = np.array([abs(np.corrcoef(rng.permutation(rx), ry)[0, 1])
                     for _ in range(20000)])
    return rho, float((null >= abs(rho)).mean())


def main():
    blob = json.loads((OUT / "results.json").read_text())
    arms = {k: v for k, v in blob["arms"].items() if k.startswith("channel-")}
    control = {k: v for k, v in blob["arms"].items() if not k.startswith("channel-")}

    names = sorted(arms, key=lambda n: arms[n]["stage0"])
    print(f"{'bucket':13}{'stage0':>8}{'gap':>8}{'recs':>6}{'bouts':>7}"
          f"{'human':>7}{'flat':>8}{'birdnet':>9}")
    for name in names:
        row = arms[name]
        print(f"{name:13}{row['stage0']:8.3f}{row['gap']:+8.3f}"
              f"{row['recordings']:6d}{row['bouts']:7d}"
              f"{row['human']:7.3f}{row['flatness']:8.4f}{row['birdnet']:9.3f}")
    for name, row in control.items():
        print(f"\n{name}: stage-0 {row['stage0']:.3f} ({row['gap']:+.3f})")
    print(f"real audio (0046): {TARGET:.3f}")

    churn = [arms[n]["stage0"] for n in names]
    print(f"\nspread across {len(names)} pinned buckets: "
          f"{max(churn) - min(churn):.4f}")

    print(f"\n{'predictor':14}{'rho':>8}{'perm p':>9}")
    for key in ("recordings", "bouts", "human", "flatness", "birdnet"):
        rho, p = spearman([arms[n][key] for n in names], churn)
        print(f"{key:14}{rho:+8.3f}{p:9.4f}")

    on_target = sorted(names, key=lambda n: abs(arms[n]["stage0"] - TARGET))
    print("\nclosest to real audio's churn:")
    for name in on_target[:3]:
        row = arms[name]
        print(f"  {name}  stage-0 {row['stage0']:.3f} ({row['gap']:+.3f})  "
              f"{row['recordings']} recordings, human {row['human']:.3f}")

    summary = {
        "target_stage0": TARGET,
        "spread": round(max(churn) - min(churn), 4),
        "ranked_by_distance_to_target": [
            {"bucket": n, "stage0": arms[n]["stage0"],
             "gap": arms[n]["gap"], "recordings": arms[n]["recordings"]}
            for n in on_target],
        "spearman_vs_churn": {
            key: dict(zip(("rho", "perm_p"),
                          [round(v, 4) for v in
                           spearman([arms[n][key] for n in names], churn)]))
            for key in ("recordings", "bouts", "human", "flatness", "birdnet")},
        "control": control,
    }
    (OUT / "analysis.json").write_text(json.dumps(summary, indent=2))
    print(f"\nanalysis -> {OUT / 'analysis.json'}")


if __name__ == "__main__":
    main()
