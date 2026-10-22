"""Attach a spoken note to a capture from a file on this machine.

The phone is the usual way in; this is the way in for everything else — a note
recorded on something other than the field app, and testing the transcription
path without a handset in the room.

Writes through the stores rather than the HTTP API on purpose: the same choice
backfill_quality.py makes, and it keeps this runnable with no device token.

    .venv/bin/python tools/add_dictation.py 145 ~/memo.wav
    .venv/bin/python tools/add_dictation.py "shaded flower bed" ~/memo.m4a

Then the worker picks it up:

    ../crowgpt/.venv/bin/python worker/transcribe_worker.py --once
"""

import argparse
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDSERVER = HERE.parent
sys.path.insert(0, str(FIELDSERVER / "src"))

from fieldserver.core.paths import database_path  # noqa: E402
from fieldserver.stores.captures import CaptureStore  # noqa: E402
from fieldserver.stores.dictations import DictationStore  # noqa: E402


def resolve_capture(db, captures, wanted: str) -> dict:
    """By server id, or by a fragment of the name — how captures are referred to.

    The id is what everything else in this project uses; the name fragment is
    what a person actually remembers about a recording. Read directly, the way
    the label-set skill resolves one: a name search is not something the store
    owes anybody, and inventing a method for one tool is worse than a query.
    """
    if wanted.isdigit():
        found = captures.get(int(wanted))
        if not found:
            raise SystemExit(f"no capture {wanted}")
        return found
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    matches = [dict(r) for r in conn.execute(
        "SELECT * FROM captures WHERE name LIKE ? ORDER BY id DESC LIMIT 10",
        (f"%{wanted}%",))]
    conn.close()
    if not matches:
        raise SystemExit(f"no capture whose name contains {wanted!r}")
    if len(matches) > 1:
        names = "\n  ".join(f"#{c['id']}  {c['name']}" for c in matches)
        raise SystemExit(f"{wanted!r} matches several captures:\n  {names}")
    return matches[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", help="server id, or part of the capture's name")
    parser.add_argument("audio", type=Path, help="the recording of somebody talking")
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--locale", default="en")
    args = parser.parse_args(argv)

    if not args.audio.exists():
        raise SystemExit(f"no file at {args.audio}")

    db = database_path(args.db)
    captures = CaptureStore(db)
    store = DictationStore(db, db.parent / "dictations")

    capture = resolve_capture(db, captures, args.capture)
    data = args.audio.read_bytes()
    row = store.create(capture_id=capture["id"],
                       contributor_id=capture.get("contributor_id"),
                       device_id=capture.get("device_id"),
                       format=args.audio.suffix.lstrip(".").lower() or "wav",
                       locale=args.locale)
    # Written in one go rather than in chunks: the resumable path is for a phone
    # on a bad link, and a file already on this disk has no link to drop.
    store.append(row["id"], data, 0)
    row = store.finalize(row["id"])
    job = store.enqueue(row["id"], capture["id"])

    print(f"capture #{capture['id']}  {capture.get('name') or ''}".rstrip())
    print(f"dictation {row['id']}: {len(data)} bytes at {store.path(row)}")
    print(f"job {job['id']}: {job['state']}")
    print("\nrun the worker to transcribe it:\n"
          "  ../crowgpt/.venv/bin/python worker/transcribe_worker.py --once")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
