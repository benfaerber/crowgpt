"""0064's verdict: merge the sitting's two instruments and settle the bet.

Block 1: 20 ternary trials from the archived PairPage
(results/listening/pairwise-0064/pairwise-gbw81btt.json), winner_arm explicit.
Blocks 2-3: 40 graded trials from pool `scrape-v3-0064`, grade signed toward
the FIRST clip (+ = first closer, checked against the page's own button
labels before this ran — a mirrored sign here would flip the verdict and
look exactly as plausible).

Outputs P(v3 preferred) over decided compares with a Wilson interval, the
graded margin from the pool trials alone, catch accuracy across all ten,
first-heard bias, and defect-tag counts per arm.
"""
import json
import sqlite3
from collections import Counter
from math import sqrt
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BLOCK1 = REPO / "crowgpt" / "results" / "listening" / "pairwise-0064" / "pairwise-gbw81btt.json"
DB = REPO / "fieldserver" / "instance" / "field.db"
OUT = Path(__file__).resolve().parent


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, centre - half, centre + half)


def main():
    v3 = v2 = ties = 0
    catch_real = catch_total = 0
    first_chosen = decided_order = 0
    defects = {"v3-scrape": Counter(), "v2-fair-k8": Counter()}
    margins = []

    block1 = json.loads(BLOCK1.read_text())
    for t in block1["trials"]:
        if t["catch"]:
            catch_total += 1
            catch_real += t["winner_arm"] == "real"
            continue
        if t["chose"] == "tie":
            ties += 1
            continue
        v3 += t["winner_arm"] == "v3-scrape"
        v2 += t["winner_arm"] == "v2-fair-k8"
        chose_side = t["chose"]
        first_chosen += chose_side == t["played_first"]
        decided_order += 1

    db = sqlite3.connect(DB)
    rows = list(db.execute(
        """SELECT t.kind, t.first_arm, t.second_arm, a.grade, a.defects
           FROM listening_answers a JOIN listening_trials t ON t.id = a.trial_id
           JOIN listening_pools p ON p.id = t.pool_id
           WHERE p.name = 'scrape-v3-0064'"""))
    for kind, first_arm, second_arm, grade, defect_json in rows:
        winner = first_arm if grade > 0 else (second_arm if grade < 0 else None)
        if kind == "catch":
            catch_total += 1
            catch_real += winner == "real"
            continue
        if winner is None:
            ties += 1
        elif winner == "v3-scrape":
            v3 += 1
        else:
            v2 += 1
        if grade != 0:
            first_chosen += grade > 0
            decided_order += 1
        toward_v3 = grade if first_arm == "v3-scrape" else -grade
        margins.append(toward_v3)
        loser = second_arm if winner == first_arm else first_arm
        for tag in json.loads(defect_json or "[]"):
            # a defect tag describes what was heard; attribute to the loser
            # only when there was a loser, else both arms wear it
            for arm in ([loser] if winner else [first_arm, second_arm]):
                if arm in defects:
                    defects[arm][tag] += 1

    decided = v3 + v2
    p, lo, hi = wilson(v3, decided)
    p_first, f_lo, f_hi = wilson(first_chosen, decided_order)
    mean_margin = sum(margins) / len(margins) if margins else 0.0

    results = {
        "compares": {"decided": decided, "v3": v3, "v2": v2, "ties": ties},
        "p_v3_preferred": {"p": round(p, 3), "ci": [round(lo, 3), round(hi, 3)]},
        "graded_margin_toward_v3_pool_only": {
            "mean": round(mean_margin, 3), "n": len(margins),
            "distribution": dict(Counter(margins))},
        "catch": {"real_preferred": catch_real, "of": catch_total},
        "first_heard_bias": {"p": round(p_first, 3),
                             "ci": [round(f_lo, 3), round(f_hi, 3)],
                             "n": decided_order},
        "defect_tags": {arm: dict(c) for arm, c in defects.items()},
    }
    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
