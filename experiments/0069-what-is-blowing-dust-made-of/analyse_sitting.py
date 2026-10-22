"""The dust sitting's verdict: does the ear ratify the grid's T1.1/k200?

Same machinery as 0067's second-sitting analysis — grades toward the FIRST
clip, catches as calibration, note halves parsed into defect families and
crossed with arm identity — plus the cell this sitting exists to fill:
which arm wears the dust words. Arms are "hot" (T1.1/k200) and "default"
(T1.0/k200), same model, same max_frames; the 0044 length check still runs
because EOS lands where it lands.

The final 8 trials ran back-to-back with dose 2 at Ben's request (cooldown
30 -> 0, 2026-08-12), the second sitting running the same deviation — the
block plan that caused it is retired per the no-tail-doses rule.
"""
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from math import sqrt
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "experiments"
                       / "0067-does-context-length-unlock-the-structure"))

from analyse_sitting2 import split_note, wilson

DB = REPO / "fieldserver" / "instance" / "field.db"
OUT = Path(__file__).resolve().parent

FAMILIES = {
    "blowing-dust": ("dust", "bellow", "breath", "accordian", "accordion",
                     "blow"),
    "hoarse2": ("hoarse2",),
    "hoarse": ("hoarse",),
    "machine": ("robo", "robot", "modem", "xylophone", "xelophone",
                "cylophone", "beep", "computer", "alien", "sci fi", "buzz"),
    "scratchy-static": ("scratchy", "static"),
    "clean": ("real", "clean", "crisp", "natural", "good", "amazing",
              "plausible"),
}


def families_of(text):
    lowered = text.lower()
    found = {family for family, words in FAMILIES.items()
             if any(w in lowered for w in words)}
    # hoarse2 is its own word; a bare "hoarse" hit inside it is not hoarse1.
    if "hoarse2" in found:
        found.discard("hoarse")
    if "clean" in found and __import__("re").search(
            r"not real|fake|not a real|can tell not", lowered):
        found.discard("clean")
    return found


def main():
    db = sqlite3.connect(DB)
    rows = list(db.execute(
        """SELECT t.kind, t.first_arm, t.second_arm, a.grade, a.defects,
                  t.facts, a.note, a.answered_at
           FROM listening_answers a
           JOIN listening_trials t ON t.id = a.trial_id
           JOIN listening_pools p ON p.id = t.pool_id
           WHERE p.name = 'dust-0069' ORDER BY a.answered_at"""))

    hot_w = default_w = ties = catch_real = catch_n = 0
    longer_pref = longer_n = 0
    margins, tags = [], Counter()
    words = defaultdict(Counter)
    described = 0
    for kind, first, second, grade, defect_json, facts_json, note, _ in rows:
        winner = first if grade > 0 else (second if grade < 0 else None)
        for tag in json.loads(defect_json or "[]"):
            tags[tag] += 1
        parts = split_note(note)
        if parts:
            described += 1
            for arm, text in ((first, parts[0]), (second, parts[1])):
                for family in families_of(text):
                    words[arm][family] += 1
        if kind == "catch":
            catch_n += 1
            catch_real += winner == "real"
            continue
        facts = json.loads(facts_json or "{}")
        if winner is None:
            ties += 1
        elif winner == "hot":
            hot_w += 1
        else:
            default_w += 1
        margins.append(grade if first == "hot" else -grade)
        if winner and facts and facts["hot_s"] != facts["default_s"]:
            longer = "hot" if facts["hot_s"] > facts["default_s"] else "default"
            longer_pref += winner == longer
            longer_n += 1

    stamps = [datetime.fromisoformat(r[7]) for r in rows]
    gaps = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:])]

    decided = hot_w + default_w
    results = {
        "compares": {"decided": decided, "hot": hot_w,
                     "default": default_w, "ties": ties},
        "p_hot": wilson(hot_w, decided),
        "graded_margin_toward_hot": {
            "mean": round(sum(margins) / len(margins), 3) if margins else 0,
            "distribution": {str(k): v for k, v in sorted(Counter(margins).items())}},
        "length_check_p_longer_preferred": wilson(longer_pref, longer_n),
        "catch": {"real_preferred": catch_real, "of": catch_n},
        "defect_tags": dict(tags),
        "described_trials": described,
        "note_families_by_arm": {arm: dict(c) for arm, c in sorted(words.items())},
        "dose_breaks_minutes": [round(g / 60, 1) for g in gaps if g > 300],
    }
    (OUT / "sitting-results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
