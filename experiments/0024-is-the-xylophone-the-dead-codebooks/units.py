"""Does the generator make single-caw bouts, or only crowds?

From the second listening sitting, unprompted: "I have noticed there are single
`blips` where one caw happens and I typically think those are AI but they turn
out to be real." That is a systematic error in one direction, which makes it a
claim about the audio rather than about the listener — if real bouts contain
lone caws and generated ones almost never do, the tell is a real defect and it
is measurable without asking anyone to listen again.

THE SAME DETECTOR ON BOTH SIDES. `Segmenter` is 0013's burst detector at its
validated 12 dB, the numerics that cut the corpus in the first place, so real and
generated units are counted by identical machinery. Anything else would measure
the detector.

THE SHAPE IS THE CLAIM, not the mean. Two distributions can share an average
while one of them has no 1-unit tail at all, and the missing tail is exactly what
"single blips read as AI" predicts.

Runs on the 60 clips already cached from the listening sitting — thirty real
held-out bouts and thirty generated, matched by condition. No GPU, no
generation.
"""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "crowgpt"
sys.path.insert(0, str(HERE / "src"))

import numpy as np

from crowgpt.segment import Segmenter

RESULTS = HERE / "results"
CACHE = "clips-sweep-0023-batch-32-dropout-0-american-crow"
OUT = Path(__file__).resolve().parent / "units.json"
SAMPLE_RATE = 24000


def main():
    clips = json.loads((RESULTS / f"{CACHE}.json").read_text())
    audio = np.load(RESULTS / f"{CACHE}.npz")
    segmenter = Segmenter()

    counts = {"A_real": [], "C_generated": []}
    for clip in clips:
        arm = clip["arm"]
        if arm not in counts:
            continue
        samples = np.asarray(audio[str(clip["clip_id"])], dtype=np.float32)
        _, units = segmenter.segment(samples, SAMPLE_RATE)
        counts[arm].append(len(units))

    report = {}
    for arm, values in counts.items():
        values = np.array(values)
        histogram = Counter(int(v) for v in values)
        report[arm] = {
            "clips": int(values.size),
            "mean_units": round(float(values.mean()), 2) if values.size else None,
            "median_units": float(np.median(values)) if values.size else None,
            "single_unit_share": round(float((values <= 1).mean()), 3) if values.size else None,
            "histogram": {str(k): histogram[k] for k in sorted(histogram)},
        }

    real, made = np.array(counts["A_real"]), np.array(counts["C_generated"])
    if real.size and made.size:
        from scipy import stats
        # Mann-Whitney rather than a t-test: unit counts are small integers and
        # the claim is about the shape of the distribution, not its centre.
        u = stats.mannwhitneyu(real, made, alternative="two-sided")
        report["comparison"] = {
            "real_single_share": report["A_real"]["single_unit_share"],
            "generated_single_share": report["C_generated"]["single_unit_share"],
            "mannwhitney_p": round(float(u.pvalue), 4),
            "significant": bool(u.pvalue < 0.05),
        }

    OUT.write_text(json.dumps(report, indent=2) + "\n")
    for arm in ("A_real", "C_generated"):
        r = report[arm]
        bars = " ".join(f"{k}:{v}" for k, v in r["histogram"].items())
        print(f"{arm:<14} n={r['clips']:<4} mean {r['mean_units']:<5} "
              f"median {r['median_units']:<5} single {r['single_unit_share']:.0%}   {bars}")
    if "comparison" in report:
        print("\n" + json.dumps(report["comparison"], indent=2))


if __name__ == "__main__":
    main()
