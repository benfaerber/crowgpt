"""The second sitting's verdict, and the cargo: whose clips wear which words.

Same core as analyse_sitting.py (grades signed toward the FIRST clip, 0044
length check before belief, catches as ear-calibration), plus what this
sitting was actually for: Ben wrote per-clip descriptions in the note field
("1. ... 2. ...") and those parse into defect families that can finally be
crossed with arm identity — which no pairwise statistic ever shows.

The parsing is keyword heuristics over his own vocabulary and says so in
the output; anything ambiguous ("lq real hq fake") is dropped rather than
guessed. Trials answered back-to-back with the previous dose are counted —
the pool's cooldown was dropped for the final 8 at Ben's request
(2026-08-11, leaving in 15 minutes), and the deviation belongs in the
record rather than hidden by it.
"""
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from math import sqrt
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "fieldserver" / "instance" / "field.db"
OUT = Path(__file__).resolve().parent

FAMILIES = {
    "blowing-dust": ("dust", "bellow", "breath", "accordian", "accordion",
                     "blow"),
    "machine": ("robo", "robot", "modem", "xylophone", "xelophone",
                "cylophone", "beep", "computer", "alien"),
    "hoarse": ("hoarse",),
    "scratchy-static": ("scratchy", "static"),
    "clean": ("real", "clean", "crisp", "natural", "good", "plausible"),
}
AMBIGUOUS = re.compile(r"lq real|hq fake|real lq|fake hq")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(p, 3), round(c - h, 3), round(c + h, 3))


def split_note(note):
    """Ben's per-clip format: '1. ... 2. ...' (or '1: ... 2:'). None if absent."""
    if not note:
        return None
    match = re.search(r"1[.:]\s*(.*?)\s*2[.:]\s*(.*)", note, re.DOTALL)
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def families_of(text):
    lowered = text.lower()
    if AMBIGUOUS.search(lowered):
        return set()
    found = {family for family, words in FAMILIES.items()
             if any(w in lowered for w in words)}
    # "real" inside a negation ("not real", "fake") is not a clean verdict.
    if "clean" in found and re.search(r"not real|fake|too .* to be real", lowered):
        found.discard("clean")
    return found


def preference(rows):
    long_w = units_w = ties = 0
    catch_real = catch_n = 0
    longer_pref = longer_n = 0
    margins, defects = [], Counter()
    for kind, first, second, grade, defect_json, facts_json, *_ in rows:
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
    return {
        "compares": {"decided": decided, "longctx": long_w,
                     "units": units_w, "ties": ties},
        "p_longctx": wilson(long_w, decided),
        "graded_margin_toward_longctx": {
            "mean": round(sum(margins) / len(margins), 3) if margins else 0,
            "distribution": {str(k): v for k, v in sorted(Counter(margins).items())}},
        "length_check_p_longer_preferred": wilson(longer_pref, longer_n),
        "catch": {"real_preferred": catch_real, "of": catch_n},
        "defect_tags": dict(defects),
    }


def main():
    db = sqlite3.connect(DB)

    def rows_of(pool):
        return list(db.execute(
            """SELECT t.kind, t.first_arm, t.second_arm, a.grade, a.defects,
                      t.facts, a.note, a.answered_at
               FROM listening_answers a
               JOIN listening_trials t ON t.id = a.trial_id
               JOIN listening_pools p ON p.id = t.pool_id
               WHERE p.name = ? ORDER BY a.answered_at""", (pool,)))

    first_sitting = rows_of("longctx-0067")
    second = rows_of("longctx-0067b")

    results = {"second_sitting": preference(second)}

    pooled = first_sitting + second
    p = preference(pooled)
    results["pooled_both_sittings"] = {
        "compares": p["compares"], "p_longctx": p["p_longctx"],
        "graded_margin_toward_longctx": p["graded_margin_toward_longctx"],
        "catch": p["catch"],
    }

    words = defaultdict(Counter)
    described = 0
    for kind, first, second_arm, grade, _, _, note, _ in second:
        parts = split_note(note)
        if not parts:
            continue
        described += 1
        for arm, text in ((first, parts[0]), (second_arm, parts[1])):
            for family in families_of(text):
                words[arm][family] += 1
    results["described_trials"] = described
    results["note_families_by_arm"] = {
        arm: dict(counter) for arm, counter in sorted(words.items())}
    results["note_families_note"] = (
        "keyword heuristics over Ben's own words; per-clip halves of his "
        "'1. ... 2. ...' notes; ambiguous lq-real/hq-fake halves dropped")

    stamps = [datetime.fromisoformat(r[7]) for r in second]
    gaps = [(b - a).total_seconds() for a, b in zip(stamps, stamps[1:])]
    breaks = [round(g / 60, 1) for g in gaps if g > 300]
    results["dose_breaks_minutes"] = breaks
    results["cooldown_deviation"] = (
        "final 8 trials taken immediately after dose 2 at Ben's request; "
        "cooldown_minutes set 30 -> 0 on 2026-08-11")

    (OUT / "sitting2-results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
