#!/usr/bin/env python3
"""Read a machine's transcript of a spoken note, and stand behind it.

This is the line between two different kinds of claim, and crossing it is meant
to take a person. Until it runs, a transcript is what a model heard: `label-set`
renders it under a hedge naming exactly what speech recognition gets wrong —
names, counts, species. After it runs, the words are an `observations` row with
source='voice', which `label-set` weighs above everything the model produced,
because somebody read them and said so.

    confirm_dictation.py 150                     # show what is waiting
    confirm_dictation.py 150 --note 4            # confirm one, as transcribed
    confirm_dictation.py 150 --note 4 --text "Edgar was on the wire"
    confirm_dictation.py "flower bed" --note 4 --stdin

CORRECT IT ON THE WAY THROUGH. What gets promoted is what you stand behind, not
what the model produced — so a mis-heard crow name is fixed here or it is
testimony forever. Confirming twice updates the note rather than filing a second
account of the same thirty seconds.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDSERVER = HERE.parent
sys.path.insert(0, str(FIELDSERVER / "src"))

from fieldserver.core.paths import database_path  # noqa: E402
from fieldserver.stores.dictations import DictationStore  # noqa: E402
from fieldserver.stores.observations import ObservationStore  # noqa: E402


def resolve_capture(db, wanted: str) -> dict:
    """An id, or part of a name — the same handle capture_facts.py takes."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        if wanted.isdigit():
            row = conn.execute("SELECT * FROM captures WHERE id = ?",
                               (int(wanted),)).fetchone()
            if not row:
                raise SystemExit(f"no capture {wanted}")
            return dict(row)
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM captures WHERE name LIKE ? ORDER BY id DESC LIMIT 10",
            (f"%{wanted}%",))]
    finally:
        conn.close()
    if not rows:
        raise SystemExit(f"no capture whose name contains {wanted!r}")
    if len(rows) > 1:
        names = "\n  ".join(f"#{r['id']}  {r['name']}" for r in rows)
        raise SystemExit(f"{wanted!r} matches several captures:\n  {names}")
    return rows[0]


def show(notes: list[dict]) -> None:
    if not notes:
        print("no spoken notes on this capture")
        return
    for note in notes:
        stamp = "confirmed" if note["confirmed_at"] else "unconfirmed"
        length = f"{note['duration_sec']:.0f}s" if note["duration_sec"] else "?"
        print(f"\n--- note {note['id']}  ({length}, {stamp}) ---")
        if note["transcript"]:
            print(note["transcript"])
            # The confidence is shown because it is the only number that says
            # anything about how much to trust the words, and it is easy to
            # forget that a fluent transcript can be a confident guess.
            if note["mean_logprob"] is not None:
                print(f"\n[{note['transcript_model']} · "
                      f"mean logprob {note['mean_logprob']:.2f}]")
        else:
            print("(not transcribed yet)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", help="server id, or part of the capture's name")
    parser.add_argument("--note", type=int, help="which dictation id to confirm")
    parser.add_argument("--text", help="the corrected wording, if it needs one")
    parser.add_argument("--stdin", action="store_true", help="read the wording from stdin")
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)

    db = database_path(args.db)
    store = DictationStore(db, db.parent / "dictations")
    observations = ObservationStore(db)

    capture = resolve_capture(db, args.capture)
    notes = store.for_capture(capture["id"])

    if args.note is None:
        print(f"capture #{capture['id']}  {capture.get('name') or ''}".rstrip())
        show(notes)
        if notes:
            print("\nconfirm one with:  --note <id>  [--text '...' | --stdin]")
        return 0

    note = next((n for n in notes if n["id"] == args.note), None)
    if not note:
        raise SystemExit(f"capture #{capture['id']} has no note {args.note}")
    if not note["transcript"]:
        raise SystemExit(f"note {args.note} has not been transcribed yet")

    body = sys.stdin.read() if args.stdin else (args.text or note["transcript"])
    body = (body or "").strip()
    if not body:
        raise SystemExit("cannot confirm an empty note")

    # Re-uses the note's own observation row when there is one, so confirming a
    # second time is a correction rather than a second account of the same
    # thirty seconds.
    existing = note["observation_id"] and observations.get(note["observation_id"])
    if existing:
        obs = observations.update_body(note["observation_id"], body)
    else:
        obs = observations.add(
            capture_id=capture["id"],
            contributor_id=note["contributor_id"] or capture["contributor_id"],
            device_id=note["device_id"] or capture["device_id"],
            body=body, source="voice", locale=note["locale"])
    store.confirm(note["id"], obs["contributor_id"], obs["id"])

    print(f"note {note['id']} confirmed as observation {obs['id']} "
          f"on capture #{capture['id']}")
    if body != note["transcript"]:
        print("(corrected on the way through — the note keeps the raw transcript)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
