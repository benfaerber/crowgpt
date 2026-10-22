"""The pre-specified analysis of 0053, and nothing else.

Every test here is named in ANALYSIS.md, which was written at 50 of 120 with
nothing read and amended at 110 before this ran. Anything not in that plan is
printed under DESCRIPTIVE and carries no threshold, because a test chosen after
seeing the data is a way of dressing up whatever happened to show.
"""
import json
import sqlite3
import sys
from math import comb
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fieldserver" / "src"))

OUT = Path(__file__).resolve().parent

#: Stage-0 churn per arm (0051) and real audio's (0046). The gap is the score the
#: trend test uses, and "nearer real" is what a preference is counted toward.
CHURN = {"channel-000": 0.927, "channel-205": 0.859, "channel-081": 0.722}
REAL_CHURN = 0.868

ALPHA = 0.05          # unspent: no interim look was taken. See the amendment.
CATCH_GATE = 0.80


def sign_test(k, n):
    """Two-sided exact binomial against 0.5."""
    if n == 0:
        return 1.0
    tail = sum(comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def cochran_armitage(counts, sizes, scores):
    """Do the proportions rise with the score? Returns (z, p)."""
    from math import erfc, sqrt

    n = sum(sizes)
    k = sum(counts)
    if n == 0 or k in (0, n):
        return 0.0, 1.0
    pbar = k / n
    num = sum(c * s for c, s in zip(counts, scores)) - pbar * sum(
        sz * s for sz, s in zip(sizes, scores))
    var = pbar * (1 - pbar) * (
        sum(sz * s * s for sz, s in zip(sizes, scores))
        - sum(sz * s for sz, s in zip(sizes, scores)) ** 2 / n)
    if var <= 0:
        return 0.0, 1.0
    z = num / sqrt(var)
    return z, erfc(abs(z) / sqrt(2))


def nearer_real(arm_a, arm_b):
    """Of two arms, the one whose churn sits closer to real audio."""
    return min((arm_a, arm_b), key=lambda a: abs(CHURN[a] - REAL_CHURN))


def main():
    from fieldserver.core.paths import database_path
    from fieldserver.stores.listening import ListeningStore

    store = ListeningStore(database_path(None))
    pool = store.pool_by_name("churn-spread-0053")
    rows = store.rows(pool["id"])

    conn = sqlite3.connect(database_path(None))
    conn.row_factory = sqlite3.Row

    compare = [r for r in rows if r["kind"] == "compare"]
    catch = [r for r in rows if r["kind"] == "catch"]

    print(f"0053 — {len(rows)} trials answered of {pool['trials']}")
    print(f"  {len(compare)} comparisons, {len(catch)} catch\n")

    # --- validity gate, before anything else ---
    caught = sum(1 for r in catch if r["preferred_arm"] == "real")
    rate = caught / len(catch) if catch else 0.0
    print(f"VALIDITY — catch trials: {caught}/{len(catch)} = {rate:.0%} "
          f"(gate {CATCH_GATE:.0%})")
    if rate < CATCH_GATE:
        print("  INVALID: reported as a broken sitting, not as a result.")
        return
    print("  passes\n")

    def pair_rows(a, b):
        want = {a, b}
        return [r for r in compare
                if {r["first_arm"], r["second_arm"]} == want]

    pairs = [("channel-000", "channel-081"), ("channel-205", "channel-081"),
             ("channel-000", "channel-205")]

    summary = {"n_answered": len(rows), "catch": [caught, len(catch)],
               "alpha": ALPHA, "pairs": {}}

    print("PER PAIR — preference for the arm nearer real churn")
    print(f"{'pair':>26}{'gap':>7}{'n':>5}{'ties':>6}{'k/m':>8}{'rate':>7}"
          f"{'95% CI':>16}{'p':>9}")
    for a, b in pairs:
        rs = pair_rows(a, b)
        target = nearer_real(a, b)
        ties = sum(1 for r in rs if r["preferred_arm"] is None)
        decided = [r for r in rs if r["preferred_arm"] is not None]
        k = sum(1 for r in decided if r["preferred_arm"] == target)
        m = len(decided)
        p = sign_test(k, m)
        lo, hi = wilson(k, m)
        gap = abs(CHURN[a] - CHURN[b])
        label = f"{a.split('-')[1]} vs {b.split('-')[1]} -> {target.split('-')[1]}"
        print(f"{label:>26}{gap:>7.3f}{len(rs):>5}{ties:>6}"
              f"{f'{k}/{m}':>8}{(k/m if m else 0):>7.2f}"
              f"   [{lo:.2f},{hi:.2f}]{p:>9.4f}")
        summary["pairs"][f"{a}|{b}"] = {
            "churn_gap": round(gap, 3), "nearer_real": target,
            "n": len(rs), "ties": ties, "k": k, "m": m,
            "rate": round(k / m, 4) if m else None,
            "ci": [round(lo, 4), round(hi, 4)], "p": round(p, 6)}

    primary = summary["pairs"]["channel-000|channel-081"]
    print(f"\nPRIMARY (pre-specified) — the widest gap, 000 vs 081")
    print(f"  {primary['k']}/{primary['m']} preferred "
          f"{primary['nearer_real']}, p = {primary['p']:.4f}, alpha = {ALPHA}")
    print(f"  -> {'RESOLVED' if primary['p'] < ALPHA else 'not resolved'}")

    scores = [abs(CHURN[a] - CHURN[b]) for a, b in pairs]
    counts = [summary["pairs"][f'{a}|{b}']["k"] for a, b in pairs]
    sizes = [summary["pairs"][f'{a}|{b}']["m"] for a, b in pairs]
    z, p_trend = cochran_armitage(counts, sizes, scores)
    print(f"\nSECONDARY (pre-specified) — Cochran-Armitage trend on churn gap")
    print(f"  z = {z:+.3f}, p = {p_trend:.4f}")
    print(f"  -> {'RESOLVED' if p_trend < ALPHA else 'not resolved'}")
    summary["trend"] = {"z": round(z, 4), "p": round(p_trend, 6)}

    # --- descriptive, no thresholds ---
    print("\nDESCRIPTIVE (no thresholds, not pre-specified as tests)")
    ties_all = sum(1 for r in compare if r["preferred_arm"] is None)
    print(f"  tie rate: {ties_all}/{len(compare)} = {ties_all/len(compare):.0%}")
    margins = [r["margin"] for r in compare if r["margin"]]
    if margins:
        strong = sum(1 for m in margins if m == 2)
        print(f"  of {len(margins)} decided, {strong} were 'much closer' "
              f"({strong/len(margins):.0%})")
    eng = [r["engaged_ms"] for r in compare if r["engaged_ms"]]
    if eng:
        eng.sort()
        print(f"  engaged time: median {eng[len(eng)//2]/1000:.1f}s "
              f"over {len(eng)} trials")
    tags = {}
    for r in rows:
        for t in r["defects"]:
            tags[t] = tags.get(t, 0) + 1
    print(f"  defect tags: {tags or 'none'}")
    notes = [r["note"] for r in rows if r["note"]]
    for n in notes:
        print(f"  note: {n!r}")
    summary["descriptive"] = {
        "tie_rate": round(ties_all / len(compare), 4),
        "defect_tags": tags, "notes": notes,
        "engaged_median_ms": eng[len(eng) // 2] if eng else None}

    (OUT / "result.json").write_text(json.dumps(summary, indent=2))
    print(f"\n-> {OUT / 'result.json'}")


if __name__ == "__main__":
    main()
