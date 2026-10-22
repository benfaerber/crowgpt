#!/usr/bin/env python3
"""Turn samples.csv into the numbers the README quotes.

Rate comes from a least-squares fit over every sample rather than first-minus-
last: the coulomb counter quantises to 2500 uAh steps on this handset, so two
endpoints can disagree with the trend by a step in either direction.

    python3 analyze.py [--capacity-mah 4810]
"""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rows(name: str) -> list[dict]:
    path = HERE / name
    if not path.exists():
        return []
    with path.open() as handle:
        return list(csv.DictReader(handle))


def num(row: dict, key: str, cast=float):
    value = row.get(key, "")
    if value in ("", "None", None):
        return None
    try:
        return cast(value)
    except ValueError:
        return None


def fit_slope(xs: list[float], ys: list[float]) -> float:
    """Least-squares slope, y units per x unit."""
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def longest_plateau(values: list[float]) -> int:
    """Longest run of identical readings, in samples."""
    best = run = 1
    for a, b in zip(values, values[1:]):
        run = run + 1 if a == b else 1
        best = max(best, run)
    return best


def series(data: list[dict], key: str) -> list[float]:
    return [v for v in (num(r, key) for r in data) if v is not None]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capacity-mah", type=float, default=4810.0,
                    help="charge_full from sysfs, not the design figure")
    args = ap.parse_args()

    data = rows("samples.csv")
    if not data:
        print("no samples.csv")
        return 1

    paired = [
        (num(r, "elapsed_s"), num(r, "charge_uah"))
        for r in data
        if num(r, "elapsed_s") is not None and num(r, "charge_uah") is not None
    ]
    elapsed = [e for e, _ in paired]
    uah = [u for _, u in paired]

    span_h = (elapsed[-1] - elapsed[0]) / 3600
    slope_per_s = fit_slope(elapsed, uah)
    rate_fit = -slope_per_s * 3600 / 1000
    rate_ends = (uah[0] - uah[-1]) / 1000 / span_h

    print(f"samples           {len(data)}  spanning {span_h*60:.1f} min")
    print(f"charge            {uah[0]/1000:.1f} -> {uah[-1]/1000:.1f} mAh "
          f"(delta {(uah[0]-uah[-1])/1000:.1f} mAh)")
    print(f"battery pct       {data[0]['battery_pct']} -> {data[-1]['battery_pct']}")
    print()
    # The counter is not smooth: it sat at one value for nine minutes and then
    # stepped 27.5 mAh when percent ticked. So report the three estimates that
    # disagree rather than the one that flatters.
    steps = [a - b for a, b in zip(uah, uah[1:]) if a != b]
    plateau = longest_plateau(uah) * (elapsed[1] - elapsed[0]) if len(elapsed) > 1 else 0
    print(f"counter steps     {len(steps)} moves, median {statistics.median(steps)/1000:.1f} mAh, "
          f"longest flat run {plateau/60:.1f} min")

    pct0, pct1 = int(data[0]["battery_pct"]), int(data[-1]["battery_pct"])
    rate_pct = (pct0 - pct1) / 100 * args.capacity_mah / span_h if pct1 != pct0 else None

    print(f"rate (fit)        {rate_fit:.1f} mAh/h")
    print(f"rate (endpoints)  {rate_ends:.1f} mAh/h")
    if rate_pct:
        print(f"rate (pct steps)  {rate_pct:.1f} mAh/h  ({pct0}->{pct1}% "
              f"at {args.capacity_mah/100:.1f} mAh per point)")
    lo, hi = min(r for r in (rate_fit, rate_ends, rate_pct) if r), \
             max(r for r in (rate_fit, rate_ends, rate_pct) if r)
    print(f"  -> {lo:.0f}-{hi:.0f} mAh/h, i.e. {args.capacity_mah/hi:.0f}-"
          f"{args.capacity_mah/lo:.0f} h to flat, {lo/args.capacity_mah*100:.1f}-"
          f"{hi/args.capacity_mah*100:.1f} %/h")

    current = series(data, "current_ua")
    if current:
        print(f"current now       median {statistics.median(current)/1000:.0f} mA "
              f"(range {min(current)/1000:.0f}..{max(current)/1000:.0f})")
        print("                  biased high: read during the adb wake this "
              "harness causes, not while idle")

    print()
    batt = series(data, "battery_c")
    print(f"battery temp      {batt[0]:.1f} -> {batt[-1]:.1f} C "
          f"(min {min(batt):.1f}, max {max(batt):.1f})")
    thermal = [int(v) for v in series(data, "thermal_status")]
    print(f"thermal status    max {max(thermal)} over {len(thermal)} samples "
          f"({'never throttled' if max(thermal) == 0 else 'THROTTLED'})")

    side = rows("thermal_sidecar.csv")
    if side:
        cpu, skin = series(side, "cpu_c"), series(side, "skin_c")
        first = int(num(side[0], "elapsed_s") or 0)
        print(f"cpu temp          {min(cpu):.1f}..{max(cpu):.1f} C  "
              f"(sidecar, from {first//60}m)")
        print(f"skin temp         {min(skin):.1f}..{max(skin):.1f} C  "
              f"(throttles at 39.0)")

    print()
    rss = series(data, "rss_kb")
    print(f"rss               {rss[0]/1024:.1f} -> {rss[-1]/1024:.1f} MB "
          f"(min {min(rss)/1024:.1f}, max {max(rss)/1024:.1f})")

    def failures(key: str) -> list[int]:
        return [int(num(r, "elapsed_s") or 0) for r in data if r.get(key) != "True"]

    for key, label in (("recording", "mic open"), ("service_up", "service up"),
                       ("adb_ok", "adb reachable")):
        bad = failures(key)
        verdict = "all samples" if not bad else \
            f"FAILED at {', '.join(f'{b//60}m{b%60:02d}s' for b in bad[:8])}"
        print(f"{label:18}{verdict}")

    pids = {r["pid"] for r in data if r["pid"]}
    print(f"{'pid':18}{'stable ' + pids.pop() if len(pids) == 1 else 'CHANGED: ' + str(pids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
