#!/usr/bin/env python3
"""Write what a model heard, about a whole recording or about one span of it.

The companion to capture_facts.py: that one reads, this one writes the single
field a model is allowed to add. Everything else on a capture belongs to the
recordist or to the analyzer.

    write_description.py "flower bed" --text "..."             # whole recording
    write_description.py "flower bed" --span 3.0 5.5 --text "..."   # one call
    write_description.py 115 --span 3.0 5.5 --clear
    write_description.py --stdin "flower bed" --span 3.0 5.5   # text on stdin

Spans are keyed on their seconds, not on a label. Re-answering a call type from
the phone deletes the label row and creates a new one, so a description hung off
a label id would disappear on a stray tap — the same way context chips already
do. Keyed on the audio, it survives the label being re-answered, retracted, or
never made, which is the whole point of writing it down before the vocabulary
changes under it.

WHAT NOT TO PUT IN IT. Not a call type — that is a label, and a human's to give.
Not an inference dressed as an observation ("the crows were angry"): say what is
audible and let whoever labels decide what it means. This text is read back to
propose labels, so anything invented here comes back later wearing the authority
of a record.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "fieldserver" / "src"))
sys.path.insert(0, str(REPO / "experiments"))

from fieldserver.stores.ai_descriptions import AiDescriptionStore  # noqa: E402
from lib.media import field_db  # noqa: E402


def resolve_capture(store, needle):
    """Same handle as capture_facts.py: an id, or part of a name.

    Names rather than ids because the app shows names, so a name is the only
    handle Ben has without a query in between.
    """
    with store._connect() as conn:
        if needle.isdigit():
            found = conn.execute("SELECT id, name FROM captures WHERE id = ?",
                                 (int(needle),)).fetchall()
        else:
            found = conn.execute(
                "SELECT id, name FROM captures WHERE name LIKE ? ORDER BY recorded_at",
                (f"%{needle}%",)).fetchall()
    if len(found) == 1:
        return found[0]["id"], found[0]["name"]
    if not found:
        raise SystemExit(f"nothing matching {needle!r} in {field_db()}")
    matches = "\n".join(f"  {r['id']}  {r['name']}" for r in found)
    raise SystemExit(f"{needle!r} matches {len(found)} captures:\n{matches}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("capture", help="capture id, or part of its name")
    parser.add_argument("--span", nargs=2, type=float, metavar=("START", "END"),
                        help="seconds; omit for the recording as a whole")
    parser.add_argument("--text", help="the description")
    parser.add_argument("--stdin", action="store_true",
                        help="read the description from stdin, for anything with newlines")
    parser.add_argument("--model", default=None,
                        help="what wrote it, e.g. 'fable-5'. Recorded, never inferred.")
    parser.add_argument("--clear", action="store_true", help="remove it instead")
    args = parser.parse_args()

    store = AiDescriptionStore(field_db())
    capture_id, name = resolve_capture(store, args.capture)
    start, end = (args.span if args.span else (None, None))
    where = "the whole recording" if start is None else f"{start}-{end}s"

    if args.clear:
        removed = store.clear(capture_id, start, end)
        print(f"{'removed' if removed else 'nothing to remove for'} {where} "
              f"on {name!r} (capture {capture_id})")
        return

    text = sys.stdin.read() if args.stdin else args.text
    if not (text or "").strip():
        raise SystemExit("nothing to write — pass --text, --stdin, or --clear")

    store.set(capture_id, text, start, end, model=args.model)
    print(f"wrote {len(text.strip())} chars for {where} on {name!r} "
          f"(capture {capture_id})")


if __name__ == "__main__":
    main()
