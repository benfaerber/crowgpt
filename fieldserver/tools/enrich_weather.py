"""Join the hour's weather to every kept capture and scout visit lacking it.

    .venv/bin/python tools/enrich_weather.py            # kept captures + visits
    .venv/bin/python tools/enrich_weather.py --all      # every capture with GPS

Idempotent: rows already enriched are skipped, so this can run after every
field session (or from a worker later) and only pays for what is new.
Open-Meteo's archive API, no key; one request per capture, hourly resolution
at the capture's own coordinates.

Kept-only by default on purpose — see the 0031 migration docstring: seeded
archive clips would join to plausible-looking local weather and poison any
analysis that forgets to filter keep.
"""

import argparse
import json
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FIELDSERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FIELDSERVER / "src"))

from fieldserver.stores.db_base import utc_now  # noqa: E402

DB = FIELDSERVER / "instance" / "field.db"
ARCHIVE = ("https://archive-api.open-meteo.com/v1/archive"
           "?latitude={lat}&longitude={lon}&start_date={day}&end_date={day}"
           "&hourly=temperature_2m,wind_speed_10m,wind_gusts_10m,"
           "precipitation,cloud_cover,surface_pressure&timezone=UTC")


def hour_of(recorded_at):
    stamp = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    return stamp.astimezone(timezone.utc)


def fetch(lat, lon, stamp):
    url = ARCHIVE.format(lat=round(lat, 4), lon=round(lon, 4),
                         day=stamp.date().isoformat())
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    hours = payload["hourly"]
    key = stamp.strftime("%Y-%m-%dT%H:00")
    try:
        i = hours["time"].index(key)
    except ValueError:
        return None
    return {
        "temp_c": hours["temperature_2m"][i],
        "wind_kmh": hours["wind_speed_10m"][i],
        "gust_kmh": hours["wind_gusts_10m"][i],
        "precip_mm": hours["precipitation"][i],
        "cloud_pct": hours["cloud_cover"][i],
        "pressure_hpa": hours["surface_pressure"][i],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true",
                        help="enrich every capture with GPS, not just kept")
    args = parser.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    keep = "" if args.all else "AND c.keep = 1"
    rows = conn.execute(f"""
        SELECT c.id, c.latitude, c.longitude, c.recorded_at
        FROM captures c
        LEFT JOIN capture_weather w ON w.capture_id = c.id
        WHERE w.capture_id IS NULL AND c.latitude IS NOT NULL
          AND c.recorded_at IS NOT NULL {keep}
        ORDER BY c.id""").fetchall()
    print(f"{len(rows)} capture(s) to enrich")

    done = failed = 0
    for row in rows:
        try:
            weather = fetch(row["latitude"], row["longitude"],
                            hour_of(row["recorded_at"]))
        except Exception as exc:  # noqa: BLE001 — one bad fetch skips one row
            print(f"  capture {row['id']}: {exc}")
            failed += 1
            continue
        if weather is None:
            print(f"  capture {row['id']}: hour not in archive yet")
            failed += 1
            continue
        conn.execute(
            "INSERT INTO capture_weather (capture_id, temp_c, wind_kmh, "
            "gust_kmh, precip_mm, cloud_pct, pressure_hpa, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row["id"], weather["temp_c"], weather["wind_kmh"],
             weather["gust_kmh"], weather["precip_mm"], weather["cloud_pct"],
             weather["pressure_hpa"], utc_now()))
        conn.commit()
        done += 1
        print(f"  capture {row['id']}: {weather['temp_c']}°C, "
              f"wind {weather['wind_kmh']} km/h")
    print(f"enriched {done}, failed {failed}")

    # Scout visits, all of them: outcome without conditions is half a label,
    # and unlike captures there is no seeded noise to fence off.
    visits = conn.execute("""
        SELECT v.id, v.latitude, v.longitude, v.visited_at
        FROM scout_visits v
        LEFT JOIN visit_weather w ON w.visit_id = v.id
        WHERE w.visit_id IS NULL AND v.latitude IS NOT NULL
          AND v.visited_at IS NOT NULL
        ORDER BY v.id""").fetchall()
    print(f"{len(visits)} visit(s) to enrich")
    done = failed = 0
    for row in visits:
        try:
            weather = fetch(row["latitude"], row["longitude"],
                            hour_of(row["visited_at"]))
        except Exception as exc:  # noqa: BLE001 — one bad fetch skips one row
            print(f"  visit {row['id']}: {exc}")
            failed += 1
            continue
        if weather is None:
            print(f"  visit {row['id']}: hour not in archive yet")
            failed += 1
            continue
        conn.execute(
            "INSERT INTO visit_weather (visit_id, temp_c, wind_kmh, "
            "gust_kmh, precip_mm, cloud_pct, pressure_hpa, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row["id"], weather["temp_c"], weather["wind_kmh"],
             weather["gust_kmh"], weather["precip_mm"], weather["cloud_pct"],
             weather["pressure_hpa"], utc_now()))
        conn.commit()
        done += 1
        print(f"  visit {row['id']}: {weather['temp_c']}°C, "
              f"wind {weather['wind_kmh']} km/h")
    print(f"enriched {done} visit(s), failed {failed}")


if __name__ == "__main__":
    main()
