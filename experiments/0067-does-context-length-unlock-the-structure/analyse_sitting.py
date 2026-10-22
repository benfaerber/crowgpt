"""The 0067 sitting's verdict: does the ear agree with the segmenter?

Grades signed toward the FIRST clip (+ = first closer), checked against the
listen page's button labels before 0064's analysis and unchanged since. The
0044 length check runs before anything is believed: per-trial durations are
in facts, so P(longer clip preferred) is computable and a length-driven
preference would disqualify the arm comparison it decorates.
"""
import json
import sqlite3
from collections import Counter
from math import sqrt
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "fieldserver" / "instance" / "field.db"
OUT = Path(__file__).resolve().parent


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(p, 3), round(c - h, 3), round(c + h, 3))


def main():
    db = sqlite3.connect(DB)
    rows = list(db.execute(
        """SELECT t.kind, t.first_arm, t.second_arm, a.grade, a.defects, t.facts
           FROM listening_answers a JOIN listening_trials t ON t.id = a.trial_id
           JOIN listening_pools p ON p.id = t.pool_id
           WHERE p.name = 'longctx-0067'"""))

    long_w = units_w = ties = 0
    catch_real = catch_n = 0
    longer_pref = longer_n = 0
    margins, defects = [], Counter()
    for kind, first, second, grade, defect_json, facts_json in rows:
        winner = first if grade > 0 else (second if grade < 0 else None)
        for tag in json.loads(defect_json or "[]"):
            defects[tag] += 1
        if kind == "catch":
            catch_n += 1
            catch_real += winner == "real"
            continue
        facts = json.loads(facts_json or "{}")
        if winner is None:
            ties += 1
        elif winner == "model-longctx":
            long_w += 1
        else:
            units_w += 1
        margins.append(grade if first == "model-longctx" else -grade)
        if winner and facts:
            longer = "model-longctx" if facts["longctx_s"] > facts["units_s"] \
                else "model-units"
            longer_pref += winner == longer
            longer_n += 1

    decided = long_w + units_w
    results = {
        "compares": {"decided": decided, "longctx": long_w,
                     "units": units_w, "ties": ties},
        "p_longctx": wilson(long_w, decided),
        "graded_margin_toward_longctx": {
            "mean": round(sum(margins) / len(margins), 3) if margins else 0,
            "distribution": dict(Counter(margins))},
        "length_check_p_longer_preferred": wilson(longer_pref, longer_n),
        "catch": {"real_preferred": catch_real, "of": catch_n},
        "defect_tags": dict(defects),
    }
    (OUT / "sitting-results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
