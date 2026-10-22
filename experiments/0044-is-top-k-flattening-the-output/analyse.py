"""What the 0044 sitting says.

Three numbers and three controls, and the controls are the half that decides
whether the numbers may be read at all.

    P(A preferred) per pairing, against a null of exactly 0.5. A forced choice
    estimates ONE quantity, so this is a binomial proportion with a Wilson
    interval and nothing has to be differenced.

    CATCH ACCURACY. Real against generated, where the answer is known. If Ben
    cannot pick real out reliably then the sitting is not measuring preference
    and neither pairing may be quoted.

    SIDE BIAS. 0041 measured Ben choosing the left clip on 65% of decided trials,
    CI [0.53, 0.75] — an effect as large as the models under test. PairPage now
    balances sides WITHIN each pairing so it cancels by construction, but that
    has to be verified per pairing rather than assumed.

    LENGTH. The arms do not have equal duration — channel256's clips are
    shorter — and "which is less robotic" could be answered by length without
    the listener noticing. Reported as the win rate of the longer clip in each
    pair, per pairing. If that is far from 0.5 the pairing is confounded.

Wilson rather than normal-approximation: at n=20 and a proportion near 0 or 1
the normal interval runs outside [0, 1] and understates the uncertainty exactly
where it matters.
"""

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def wilson(successes, total, z=1.96):
    if total == 0:
        return (0.0, 0.0, 0.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return p, max(0.0, centre - half), min(1.0, centre + half)


def sign_test(successes, total):
    """Two-sided exact binomial p against 0.5."""
    if total == 0:
        return 1.0
    def c(n, k):
        return math.comb(n, k)
    tail = sum(c(total, k) for k in range(0, min(successes, total - successes) + 1))
    return min(1.0, 2 * tail / (2 ** total))


def report(name, wins, total, subject):
    p, lo, hi = wilson(wins, total)
    resolved = lo > 0.5 or hi < 0.5
    print(f"  {name:34s} {wins:2d}/{total:2d}  P({subject}) = {p:.3f}  "
          f"95% CI [{lo:.3f}, {hi:.3f}]  p = {sign_test(wins, total):.4f}"
          f"{'  RESOLVED' if resolved else ''}")
    return {"wins": wins, "n": total, "p": p, "ci": [lo, hi],
            "exact_p": sign_test(wins, total), "resolved": resolved}


def main(paths):
    """One or more sessions. Two were sat: the same arms, redrawn and filtered.

    THEY ARE POOLED ONLY BECAUSE THE CLIPS DIFFER. The evening page was rebuilt
    with fresh seeds after the 1.0 s filter went in, so the second sitting is a
    REPLICATION on new draws rather than a re-test of audio already judged.
    Pooling two sittings of the same clips would double-count one sample.
    """
    sessions = [json.loads(Path(p).read_text()) for p in paths]
    for session in sessions:
        analyse_one(session)
    if len(sessions) > 1:
        pooled = {"session_id": "pooled", "rated": sum(s["rated"] for s in sessions),
                  "of": sum(s["of"] for s in sessions),
                  "note": f"pooled over {', '.join(s['session_id'] for s in sessions)}",
                  "trials": [t for s in sessions for t in s["trials"]]}
        print("\n" + "=" * 70)
        analyse_one(pooled, write=True)


def analyse_one(session, write=False):
    trials = session["trials"]
    out = {"session_id": session["session_id"], "note": session.get("note", ""),
           "rated": session["rated"], "of": session["of"]}

    pairings = defaultdict(list)
    for t in trials:
        key = "catch" if t["catch"] else tuple(sorted((t["left_arm"], t["right_arm"])))
        pairings[key].append(t)

    print(f"session {session['session_id']} · {session['rated']}/{session['of']} rated")
    if session.get("note"):
        print(f"note: {session['note']}")

    print("\nTHE QUESTIONS")
    out["pairings"] = {}
    for key, group in sorted(pairings.items(), key=lambda kv: str(kv[0])):
        if key == "catch":
            continue
        # Report the arm under test, not whichever happened to be stored as A.
        subject = "notopk" if "notopk" in key else "channel256"
        wins = sum(1 for t in group if t["winner_arm"] == subject)
        out["pairings"][" vs ".join(key)] = report(
            " vs ".join(key), wins, len(group), subject)

    print("\nCONTROLS")
    catch = pairings.get("catch", [])
    correct = sum(1 for t in catch if t["winner_arm"] == "real")
    out["catch"] = report("catch: real vs generated", correct, len(catch), "real")

    left = sum(1 for t in trials if t["chose"] == "left")
    out["side_bias"] = report("side: left chosen", left, len(trials), "left")

    out["side_bias_by_pairing"] = {}
    for key, group in sorted(pairings.items(), key=lambda kv: str(kv[0])):
        label = key if isinstance(key, str) else " vs ".join(key)
        lefts = sum(1 for t in group if t["chose"] == "left")
        out["side_bias_by_pairing"][label] = report(
            f"  side within {label}", lefts, len(group), "left")

    print("\nLENGTH CONFOUND")
    out["length"] = {}
    if not all("left_seconds" in t for t in trials):
        print("  not recorded in this session — PairPage gained clip durations "
              "after it was sat")
        out["length"] = None
    for key, group in sorted(pairings.items(), key=lambda kv: str(kv[0])):
        if out["length"] is None:
            break
        label = key if isinstance(key, str) else " vs ".join(key)
        decided = [t for t in group if t["left_seconds"] != t["right_seconds"]]
        longer = sum(1 for t in decided
                     if (t["chose"] == "left") == (t["left_seconds"] > t["right_seconds"]))
        out["length"][label] = report(f"  longer clip wins, {label}",
                                      longer, len(decided), "longer")

    print("\nMEDIAN CLIP LENGTH BY ARM")
    lengths = defaultdict(list)
    for t in trials:
        if "left_seconds" not in t:
            continue
        lengths[t["left_arm"]].append(t["left_seconds"])
        lengths[t["right_arm"]].append(t["right_seconds"])
    out["median_seconds"] = {}
    for arm, values in sorted(lengths.items()):
        values.sort()
        median = values[len(values) // 2]
        out["median_seconds"][arm] = median
        print(f"  {arm:12s} n={len(values):3d}  median {median:.2f}s")

    print("\nEFFORT")
    decisions = [t["decision_ms"] for t in trials if t.get("decision_ms") is not None]
    decisions.sort()
    plays = Counter()
    for t in trials:
        plays[t["plays_left"] + t["plays_right"]] += 1
    out["median_decision_ms"] = decisions[len(decisions) // 2] if decisions else None
    shown = f"{out['median_decision_ms'] / 1000:.1f}s" if decisions else "not recorded"
    print(f"  median decision {shown} · plays per trial {sorted(plays.items())}")

    if write:
        (HERE / "results.json").write_text(json.dumps(out, indent=2))
        print("\nwrote results.json")
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
