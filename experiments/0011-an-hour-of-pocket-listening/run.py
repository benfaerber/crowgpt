#!/usr/bin/env python3
"""Sample what an hour of pocket listening costs: battery, memory, heat.

The last unexercised item of the recorder audit that needs neither a failure
injected nor a microphone plugged in — just a phone left alone. It is the one
that decides whether pocket listening is a feature or a warning, because a
mode that eats a third of the battery an hour cannot be armed on the way out
of the door and forgotten.

    python3 run.py --device 192.168.1.154:5555 --minutes 60

WIRELESS ADB IS THE POINT. A phone on USB is charging, and a charging phone
cannot show drain — the level would climb while the microphone ran and the
measurement would read as free. So the handset must be unplugged, which means
it has to be reachable over wifi.

Every sample is written to samples.csv as it is taken and the latest line is
printed, so an hour-long run can be watched or abandoned without losing what
it has already learned.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, fields
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ADB = Path.home() / "Android/Sdk/platform-tools/adb"
PACKAGE = "com.cawtalker.field"


def shell(device: str, command: str) -> str:
    """One adb shell call. Returns "" rather than raising: a sample that fails
    must not end an hour-long run — a gap in one column is worth more than
    losing the other fifty-nine minutes."""
    try:
        out = subprocess.run(
            [str(ADB), "-s", device, "shell", command],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout
    except subprocess.SubprocessError:
        return ""


def number(pattern: str, text: str, cast=int):
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        return cast(match.group(1))
    except (TypeError, ValueError):
        return None


def live_temp(thermal: str, mtype: int) -> float | None:
    """Hottest live sensor of a type, from the HAL section only.

    `dumpsys thermalservice` opens with `Cached temperatures:`, a stale snapshot
    — while unplugged for twenty minutes it still reported charging_therm at
    45C and a battery 5C hotter than the live block. Reading the first match in
    the dump therefore pinned cpu_c to a constant 58.000004 for a whole run
    while the cores were actually at 31C."""
    _, _, live = thermal.partition("Current temperatures from HAL")
    if not live:
        return None
    # Anchored on Temperature{ because CoolingDevice{ reuses the mType numbers:
    # an unanchored match read the GPU cooling level, 4798000, as a skin temp.
    values = [
        float(v)
        for v in re.findall(
            rf"Temperature\{{mValue=(-?[\d.]+(?:E-?\d+)?), mType={mtype},", live
        )
    ]
    # Absent sensors report -3.4028235E38 (float min) rather than being omitted.
    values = [v for v in values if v > -1000]
    return max(values) if values else None


def reachable(device: str) -> bool:
    """Whether adb can still talk to the handset at all.

    A wifi dropout while the phone dozes empties every column, pidof included,
    which is indistinguishable from the app having been reaped. Without this
    the run would report a reaping that never happened — the one finding it
    exists to establish."""
    return "ok" in shell(device, "echo ok")


def mic_open(flinger: str, pid: int | None) -> bool:
    """Whether an input thread is out of standby with an active record track
    owned by `pid`.

    Two spellings matter. Standby is `Standby: no` on this Android, not the
    older `standby: 0`, so the previous test never fired and logged a closed
    microphone for an hour of open one.

    Attribution matters in both directions. The dump carries a hotword input
    thread per capture path at all times, so "an input thread exists" is always
    true; and were the app reaped while Assistant held the microphone, an
    unattributed standby check would call the mic open and hide the reaping."""
    if not pid:
        return False
    track = re.compile(rf"^\s*yes\s+\d+\s+{pid}/\s*\d+")
    record_block = out_of_standby = past_live_rows = False
    for line in flinger.splitlines():
        stripped = line.lstrip()
        if stripped.lstrip("- ").startswith("Input thread"):
            # A leading dash marks a torn-down thread retained in the dump.
            record_block = "(RECORD)" in line and not stripped.startswith("-")
            out_of_standby = past_live_rows = False
            continue
        if not record_block:
            continue
        if "Local log:" in line:
            past_live_rows = True
        elif stripped == "Standby: no":
            out_of_standby = True
        elif out_of_standby and not past_live_rows and track.match(line):
            return True
    return False


@dataclass
class Sample:
    elapsed_s: int
    """Percent, which is coarse — charge_uah is what the arithmetic uses."""
    battery_pct: int | None
    """Coulomb counter in µAh. The honest measure: percent moves in 1% steps
    of ~45 mAh, so a 40-minute window can show zero change and hide the answer."""
    charge_uah: int | None
    """Instantaneous current in µA. Negative while discharging on Pixels."""
    current_ua: int | None
    battery_c: float | None
    """0 = no throttling. Anything above it is Android saying the phone is hot."""
    thermal_status: int | None
    cpu_c: float | None
    """Skin temperature, mType=3 — what Android actually throttles on, and the
    one a pocket traps. Its first throttling threshold on this handset is 39C."""
    skin_c: float | None
    """Resident set of the app process, KB — the ring buffer lives in here."""
    rss_kb: int | None
    pid: int | None
    """Whether the microphone is genuinely still open, read from audioflinger
    rather than from the app's own claim about itself."""
    recording: bool
    """Whether the foreground service that makes it legal is still up."""
    service_up: bool
    """Whether adb answered at all. False turns every other column into a gap
    rather than a reading, and must not be read as the app having died."""
    adb_ok: bool


def sample(device: str, elapsed: int) -> Sample:
    battery = shell(device, "dumpsys battery")
    thermal = shell(device, "dumpsys thermalservice")
    pid = number(r"(\d+)", shell(device, f"pidof {PACKAGE}"))
    meminfo = shell(device, f"dumpsys meminfo {PACKAGE}") if pid else ""
    # audio_flinger names an input thread per open record client; the app's own
    # isListening() would only report what the app believes.
    flinger = shell(device, "dumpsys media.audio_flinger")
    services = shell(device, f"dumpsys activity services {PACKAGE}")

    temp_c = number(r"temperature: (\d+)", battery)
    current_ua = number(r"current now: (-?\d+)", battery)
    if current_ua is None:
        # Recent Pixels dropped `current now` from dumpsys battery. The coulomb
        # counter's sibling in sysfs still carries it and needs no root.
        current_ua = number(
            r"(-?\d+)", shell(device, "cat /sys/class/power_supply/battery/current_now")
        )

    return Sample(
        elapsed_s=elapsed,
        battery_pct=number(r"^\s*level: (\d+)", battery) or number(r"level: (\d+)", battery),
        charge_uah=number(r"Charge counter: (\d+)", battery),
        current_ua=current_ua,
        battery_c=temp_c / 10 if temp_c is not None else None,
        thermal_status=number(r"Thermal Status: (\d+)", thermal),
        cpu_c=live_temp(thermal, 0),
        skin_c=live_temp(thermal, 3),
        rss_kb=number(r"Native Heap\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+)", meminfo),
        pid=pid,
        recording=mic_open(flinger, pid),
        service_up="ListeningService" in services,
        adb_ok=bool(battery.strip()),
    )


def progress(line: str) -> None:
    print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True, help="adb serial, e.g. 192.168.1.154:5555")
    ap.add_argument("--minutes", type=int, default=60)
    ap.add_argument("--every", type=int, default=30, help="seconds between samples")
    args = ap.parse_args()

    plugged = "USB powered: true" in shell(args.device, "dumpsys battery")
    if plugged:
        print(
            "REFUSING: the phone is plugged in, so it is charging and no drain can be\n"
            "measured. Unplug it — wireless adb keeps it reachable — and run again.",
            file=sys.stderr,
        )
        return 1

    out = HERE / "samples.csv"
    with out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[f.name for f in fields(Sample)])
        writer.writeheader()

        started = time.monotonic()
        deadline = started + args.minutes * 60
        first: Sample | None = None
        while True:
            elapsed = int(time.monotonic() - started)
            row = sample(args.device, elapsed)
            first = first or row
            writer.writerow(asdict(row))
            handle.flush()

            drop = None
            if first.charge_uah and row.charge_uah:
                drop = (first.charge_uah - row.charge_uah) / 1000
            progress(
                f"0011 pocket listening · {elapsed // 60}m of {args.minutes}m · "
                f"battery {row.battery_pct}% "
                f"({f'-{drop:.0f} mAh' if drop is not None else 'mAh unknown'}) · "
                f"{row.battery_c}C batt / {row.cpu_c}C cpu · thermal {row.thermal_status} · "
                f"rss {row.rss_kb} KB · mic {'OPEN' if row.recording else 'CLOSED'} · "
                f"service {'up' if row.service_up else 'DOWN'} · pid {row.pid}"
                + ("" if row.adb_ok else " · ADB UNREACHABLE, columns are gaps")
            )
            if not row.pid and reachable(args.device):
                progress(f"0011 ENDED EARLY at {elapsed // 60}m — the app process is gone.")
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(args.every)

    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
