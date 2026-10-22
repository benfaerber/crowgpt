"""Publish a scouting layer for the app's map overlay.

    .venv/bin/python tools/publish_scout.py ../experiments/0084-*/scout_layer.json

Validates the shape the app depends on — ranked targets with coordinates and
a score, owl points with coordinates — and copies into instance/scout.json,
which /api/scout serves. Publishing again replaces the layer.
"""

import json
import shutil
import sys
from pathlib import Path

FIELDSERVER = Path(__file__).resolve().parents[1]
DEST = FIELDSERVER / "instance" / "scout.json"


def validate(path):
    payload = json.loads(Path(path).read_text())
    targets = payload.get("targets")
    if not targets:
        raise SystemExit("no targets in payload")
    for t in targets:
        for key in ("rank", "lat", "lon", "score"):
            if not isinstance(t.get(key), (int, float)):
                raise SystemExit(f"target missing numeric `{key}`: {t}")
    for o in payload.get("owls", [])[:50]:
        if not isinstance(o.get("lat"), (int, float)):
            raise SystemExit(f"owl missing `lat`: {o}")
    return len(targets), len(payload.get("owls", []))


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    n, owls = validate(sys.argv[1])
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sys.argv[1], DEST)
    print(f"published {n} targets, {owls} owls -> {DEST}")


if __name__ == "__main__":
    main()
