"""What BirdNET and the call-type heads hear in the shared batch, filter by filter.

The worker ran these clips with the fleet's home-ground coordinates (the bug
fixed in f69f6e8). This reruns the analyzer on the same stored audio with no
occurrence filter, or with the coordinates given, and prints per clip which
species and call types it names. Needs the crowgpt venv (birdnetlib + heads).

    FIELD_DB=... crowgpt/.venv/bin/python experiments/0089-are-shared-instagram-clips-useful/unfiltered.py [--lat 51.5 --lon -0.12]
"""

import argparse
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "fieldserver" / "src"))

from analyzer import birdnet  # noqa: E402
from fieldserver.stores.media import MediaStore  # noqa: E402

DB = Path(os.environ.get("FIELD_DB") or REPO / "fieldserver" / "instance" / "field.db")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", default="instagram-2026-11")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    args = parser.parse_args()
    store = MediaStore(DB, DB.parent / "media")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "select c.id, l.call_type, m.* from captures c "
        "join devices d on d.id = c.device_id "
        "join media m on m.capture_id = c.id and m.kind = 'audio' "
        "left join labels l on l.capture_id = c.id "
        "where c.provenance = 'shared' and d.label = ? order by c.id", (args.batch,)).fetchall()
    for row in rows:
        calls = [c for c in birdnet.analyze(store.as_wav(dict(row)), lat=args.lat, lon=args.lon)
                 if not c.get("candidate")]
        species = Counter(c["species"] for c in calls)
        types = Counter(c["call_type"] for c in calls)
        print(f"{row['id']}  recordist: {row['call_type']:13} | {len(calls):2} calls | "
              f"{dict(species)} | {dict(types)}", flush=True)


if __name__ == "__main__":
    main()
