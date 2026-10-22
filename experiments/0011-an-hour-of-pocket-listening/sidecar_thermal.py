#!/usr/bin/env python3
"""Live skin and CPU temperature, for the part of run 0011 that has them.

The main run logged cpu_c from `Cached temperatures:`, a stale block that pinned
it to a constant 58.000004 while the cores sat at 31C. run.py is fixed, but a
running process cannot be un-run, so this samples the live HAL section alongside
for the remainder of the hour. Partial coverage on purpose — it starts whenever
it is started, and elapsed_s is shared with samples.csv so the two join.

    python3 sidecar_thermal.py --device <serial> --until-elapsed 3600
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import run

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--until-elapsed", type=int, default=3600)
    ap.add_argument("--every", type=int, default=30)
    ap.add_argument("--started-at", type=float, required=True,
                    help="unix time samples.csv began, so elapsed_s lines up")
    args = ap.parse_args()

    out = HERE / "thermal_sidecar.csv"
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["elapsed_s", "cpu_c", "skin_c", "battery_c", "thermal_status"]
        )
        writer.writeheader()
        while True:
            elapsed = int(time.time() - args.started_at)
            thermal = run.shell(args.device, "dumpsys thermalservice")
            writer.writerow({
                "elapsed_s": elapsed,
                "cpu_c": run.live_temp(thermal, 0),
                "skin_c": run.live_temp(thermal, 3),
                "battery_c": run.live_temp(thermal, 2),
                "thermal_status": run.number(r"Thermal Status: (\d+)", thermal),
            })
            handle.flush()
            if elapsed >= args.until_elapsed:
                return 0
            time.sleep(args.every)


if __name__ == "__main__":
    raise SystemExit(main())
