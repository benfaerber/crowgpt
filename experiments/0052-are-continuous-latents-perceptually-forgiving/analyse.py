"""Score the 0052 ABX sitting. Run after Ben has saved the session JSON.

    python analyse.py ../../crowgpt/results/listening/continuous-latent-0052/session-*.json

THE VERDICT IS COMPUTED, NOT READ OFF. The reading was pre-registered in the
README before the sitting, and this applies it mechanically — because the
direction the mistake runs in is always the same one, and it is the direction
that lets an expensive route go ahead. A rate a little above chance gets read as
"basically chance, so it's fine, build the model". 17/25 is 68.0%, which this
rejects at p = 0.032.

TWO DIFFERENT QUESTIONS, and they need different tests.

  Is it audible?      One-sided binomial against 0.5. Small p = he can hear it.
  Is it transparent?  NOT the same as failing the first test. Absence of evidence
                      is not equivalence; at n=25 the interval around chance
                      reaches ~0.70, so "not resolved" covers a lot. The honest
                      statement is the interval, and this prints it rather than a
                      verdict.

TWO WAYS THIS SITTING VOIDS ITSELF, and both are checked before anything else is
read.

  1. THE ANCHOR. A 2 kHz lowpass cannot be inaudible. If it does not resolve, the
     page, the audio chain or the listener was not working, and nothing else on
     the page means anything. This is 0039's rule, which it learned by choosing a
     control circularly and losing two sittings.

  2. NO POWER. If every latent arm reads chance INCLUDING +0.80 — an error level
     offline-clear of every codec ever measured here — then the page cannot see
     latent noise at any level, and "all arms transparent" is indistinguishable
     from "this test has no power". That reads as the best possible result and is
     nearly the worst. Nothing but the 0.80 arm can tell the two apart, which is
     why it is on the page.
"""
import glob
import json
import sys
from collections import defaultdict
from datetime import datetime
from math import comb, sqrt

ANCHOR = "lowpass_2k"
CEILING = "cont32"
LADDER = ["cont32+noise0.20", "cont32+noise0.40", "cont32+noise0.80"]
TOP = "cont32+noise0.80"


def wilson(hits, n, z=1.96):
    """Wilson interval — behaves at the edges, where the normal approximation does not."""
    if n == 0:
        return (0.0, 1.0)
    p = hits / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    spread = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def binomial_p(hits, n):
    """One-sided P(at least this many correct | chance), exact."""
    return sum(comb(n, k) for k in range(hits, n + 1)) / (2 ** n)


def verdict(results):
    """The pre-registered reading, applied without discretion."""
    anchor = results.get(ANCHOR)
    if not anchor:
        return "VOID", f"no {ANCHOR} arm — the sitting has no positive control."
    if anchor["p_one_sided"] >= 0.05:
        return "VOID", (
            f"the anchor did not resolve ({anchor['correct']}/{anchor['n']}). A 2 kHz "
            "lowpass cannot be inaudible, so the page, the playback chain or the "
            "sitting was broken. Read nothing else here.")

    ceiling = results.get(CEILING)
    if ceiling and ceiling["p_one_sided"] < 0.05:
        return "ROUTE DEAD", (
            f"the ceiling arm is audible ({ceiling['correct']}/{ceiling['n']}, "
            f"p={ceiling['p_one_sided']:.4f}). The continuous representation is "
            "distinguishable from raw before any model error is added, so error "
            "budgets do not matter. Stop.")

    rungs = [results[a] for a in LADDER if a in results]
    if rungs and not any(r["p_one_sided"] < 0.05 for r in rungs):
        return "NO POWER", (
            "no latent arm resolved, including +0.80 — an error level offline-clear "
            "of every codec measured in this project. This is NOT a pass: the page "
            "cannot see latent noise at any level, so 'all transparent' and 'no "
            "power' are the same reading. Fix the instrument before believing it.")

    tight = results.get("cont32+noise0.20")
    if tight and tight["p_one_sided"] < 0.05:
        return "TIGHT BUDGET", (
            f"+0.20 is audible ({tight['correct']}/{tight['n']}, "
            f"p={tight['p_one_sided']:.4f}). The representation is forgiving but not "
            "generously so: a flow model must hold under 20% per-channel error. "
            "Proceed if at all, with the model as the risk rather than the "
            "representation.")

    top = results.get(TOP)
    if top and top["p_one_sided"] < 0.05:
        return "PASS", (
            f"the ceiling and +0.20 read chance while +0.80 resolves "
            f"({top['correct']}/{top['n']}, p={top['p_one_sided']:.4f}). The listener "
            "demonstrably can hear latent error, and 20% of it is still inaudible. "
            "The budget is real and lies between. Build the model.")

    return "UNRESOLVED", (
        "the anchor passed and the ceiling is clean, but the ladder did not separate. "
        "Not a fail and not a pass — the sitting lacked the power to locate a budget.")


def main(patterns):
    paths = [p for pattern in patterns for p in sorted(glob.glob(pattern))]
    if not paths:
        raise SystemExit("no session files matched")

    arms, notes = defaultdict(list), []
    for path in paths:
        session = json.loads(open(path).read())
        if session.get("kind") != "abx":
            raise SystemExit(f"{path} is a '{session.get('kind')}' session, not abx")
        if session.get("note"):
            notes.append(session["note"])
        for trial in session["trials"]:
            if trial.get("answer"):
                arms[trial["arm"]].append(trial)

        stamps = sorted(t["answered_at"] for t in session["trials"] if t.get("answered_at"))
        if len(stamps) > 1:
            span = (datetime.fromisoformat(stamps[-1].replace("Z", "+00:00"))
                    - datetime.fromisoformat(stamps[0].replace("Z", "+00:00")))
            spent = sum(t.get("decision_ms") or 0 for t in session["trials"]) / 1000
            if span.total_seconds() > 4 * spent + 1800:
                print(f"!! {path.split('/')[-1]}: answers span {span}, of which only "
                      f"{spent/60:.1f} min were decisions.\n   A page left open across a "
                      f"day is not one sitting — this confound voided 0039's first "
                      f"attempt.\n")

    total = sum(len(v) for v in arms.values())
    print(f"{len(paths)} session(s), {total} answered trials\n")
    print(f"{'arm':20s} {'correct':>11s} {'rate':>7s} {'95% CI':>16s} {'p(chance)':>11s}  reading")

    order = [CEILING] + LADDER + [ANCHOR]
    results = {}
    for arm in [a for a in order if a in arms] + [a for a in sorted(arms) if a not in order]:
        trials = arms[arm]
        n = len(trials)
        hits = sum(bool(t["correct"]) for t in trials)
        low, high = wilson(hits, n)
        p = binomial_p(hits, n)
        reading = ("AUDIBLE" if p < 0.05
                   else f"not resolved — at most {high:.1%}")
        print(f"{arm:20s} {hits:4d} / {n:<4d} {hits/n:7.3f}   [{low:.3f}, {high:.3f}] "
              f"{p:11.4f}  {reading}")
        results[arm] = {"n": n, "correct": hits, "rate": round(hits / n, 4),
                        "ci": [round(low, 4), round(high, 4)],
                        "p_one_sided": p, "reading": reading}

    label, why = verdict(results)
    print(f"\n{'='*78}\n{label}\n{'='*78}\n{why}\n")

    # Effort, because 0039 found 1-play trials at 0.506 and 4+-play trials at
    # 0.615 — a difference he can only find by working for it is still real, and
    # is also a different claim from one he hears immediately.
    print(f"{'arm':20s} {'1 play':>10s} {'2+ plays':>10s} {'median s':>10s}")
    for arm in results:
        trials = arms[arm]
        one = [t for t in trials if (t.get("plays") or 0) <= 1]
        many = [t for t in trials if (t.get("plays") or 0) > 1]
        rate = lambda s: f"{sum(bool(t['correct']) for t in s)}/{len(s)}" if s else "—"
        secs = sorted((t.get("decision_ms") or 0) / 1000 for t in trials)
        print(f"{arm:20s} {rate(one):>10s} {rate(many):>10s} "
              f"{secs[len(secs)//2]:10.1f}")

    if notes:
        print("\nWHAT HE SAID — the most valuable output if any arm resolved:")
        for note in notes:
            print(f"  {note}")

    json.dump({"arms": results, "verdict": label, "why": why, "notes": notes},
              open("results.json", "w"), indent=2)
    print("\nwrote results.json")


if __name__ == "__main__":
    main(sys.argv[1:] or
         ["../../crowgpt/results/listening/continuous-latent-0052/session-*.json"])
