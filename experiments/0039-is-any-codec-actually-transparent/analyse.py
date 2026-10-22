"""Score an ABX sitting. Run after Ben has saved the session JSON.

    python analyse.py ../../crowgpt/results/listening/abx-0039/session-*.json

WHY THIS IS NOT EYEBALLED. "He got 58 of 90" is not an answer, and the direction
the mistake runs in is always the same one — a rate a little above 50% read as
"basically chance, so transparent". Chance is what the null predicts, and 58/90
is 64.4%, which this rejects at p = 0.004. The whole reason for running ABX was
that the previous instrument declared transparency by default; scoring it by
impression would put that straight back.

TWO DIFFERENT QUESTIONS, and they need different tests.

  Is it audible?      One-sided binomial against 0.5. Small p = he can hear it.
  Is it transparent?  NOT the same as failing the first test. Absence of
                      evidence is not equivalence, and with 90 trials the
                      interval around chance is +/-10 points, so "not resolved"
                      covers everything up to about 60%. The honest statement is
                      the interval, and this prints it rather than a verdict.

The control arm is checked first and can void the sitting. EnCodec at 6 kbps is
a difference Ben has described unprompted as scratchy; if that does not come out
clearly above chance then something is wrong with the page, the audio or the
listener that day, and the DAC number means nothing regardless of what it says.
"""
import glob
import json
import sys
from collections import defaultdict
from datetime import datetime
from math import comb, sqrt


def wilson(hits, n, z=1.96):
    """Wilson interval — behaves at the edges, where normal approximation does not."""
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


def main(patterns):
    paths = [p for pattern in patterns for p in sorted(glob.glob(pattern))]
    if not paths:
        raise SystemExit("no session files matched")

    arms = defaultdict(list)
    notes = []
    for path in paths:
        session = json.loads(open(path).read())
        if session.get("kind") != "abx":
            raise SystemExit(f"{path} is a '{session.get('kind')}' session, not abx")
        if session.get("note"):
            notes.append(session["note"])
        for trial in session["trials"]:
            arms[trial["arm"]].append(trial)

    for path in paths:
        session = json.loads(open(path).read())
        stamps = sorted(t["answered_at"] for t in session["trials"] if t.get("answered_at"))
        if len(stamps) > 1:
            span = (datetime.fromisoformat(stamps[-1].replace("Z", "+00:00"))
                    - datetime.fromisoformat(stamps[0].replace("Z", "+00:00")))
            spent = sum(t.get("decision_ms") or 0 for t in session["trials"]) / 1000
            if span.total_seconds() > 4 * spent + 1800:
                print(f"!! {path.split('/')[-1]}: answers span {span}, of which only "
                      f"{spent/60:.1f} min were decisions.\n   A page left open across "
                      f"a day is not one sitting — attention and playback conditions\n"
                      f"   do not hold still, and this is the confound that voided the "
                      f"first attempt.\n")

    print(f"{len(paths)} session(s), {sum(len(v) for v in arms.values())} trials\n")
    print(f"{'arm':12s} {'correct':>12s} {'rate':>7s} {'95% CI':>16s} {'p(chance)':>11s}  verdict")

    results = {}
    for arm, trials in sorted(arms.items()):
        n = len(trials)
        hits = sum(t["correct"] for t in trials)
        low, high = wilson(hits, n)
        p = binomial_p(hits, n)
        # No fixed "transparent" threshold, because at n=90 the upper bound is
        # 0.601 even on a perfect 45/90 — a bar of "high < 0.60" could never be
        # met and would report every result as underpowered. The upper bound is
        # itself the honest statement, so it is what gets said.
        verdict = ("AUDIBLE" if p < 0.05
                   else f"not audible — discriminability at most {high:.1%}")
        print(f"{arm:12s} {hits:5d} / {n:<4d} {hits/n:7.3f} "
              f"  [{low:.3f}, {high:.3f}] {p:11.4f}  {verdict}")
        results[arm] = {"n": n, "correct": hits, "rate": hits / n,
                        "ci": [round(low, 4), round(high, 4)],
                        "p_one_sided": p, "verdict": verdict}

    control = results.get("encodec8")
    if control:
        print()
        if control["p_one_sided"] < 0.05:
            print("CONTROL PASSES — EnCodec-8 is resolved above chance, so the page, "
                  "the audio\n  and the listener were all working. The other arm is "
                  "readable.")
        else:
            print("!! CONTROL FAILED — a difference known to be audible did not "
                  "resolve.\n  Do NOT read the other arm. Something is wrong with the "
                  "page, the playback\n  chain or the sitting; find it before "
                  "believing any transparency claim.")

    # Learning: the answer is revealed each trial, so a difference that only
    # becomes findable halfway through is still a difference that was there.
    print()
    for arm, trials in sorted(arms.items()):
        ordered = sorted(trials, key=lambda t: t["trial_index"])
        half = len(ordered) // 2
        first = sum(t["correct"] for t in ordered[:half])
        second = sum(t["correct"] for t in ordered[half:])
        plays = [t.get("plays") for t in trials if t.get("plays") is not None]
        print(f"{arm:12s} first half {first}/{half}  second half {second}/{len(ordered)-half}"
              + (f"   median plays {sorted(plays)[len(plays)//2]}" if plays else ""))

    out = "results.json"
    json.dump({"arms": results, "notes": notes}, open(out, "w"), indent=2)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["../../crowgpt/results/listening/abx-0039/session-*.json"])
