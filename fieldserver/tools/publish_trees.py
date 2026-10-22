"""Publish a tall-trees GeoJSON for the app's map overlay.

    .venv/bin/python tools/publish_trees.py ../experiments/0083-*/tall_trees.geojson

Validates the shape the app depends on — Point features with an integer `h`
(metres) — and copies into instance/trees.geojson, which /api/trees serves.
Publishing again replaces the layer; there is exactly one, on purpose.
"""

import json
import shutil
import sys
from pathlib import Path

FIELDSERVER = Path(__file__).resolve().parents[1]
DEST = FIELDSERVER / "instance" / "trees.geojson"


def validate(path):
    payload = json.loads(Path(path).read_text())
    features = payload.get("features")
    if payload.get("type") != "FeatureCollection" or not features:
        raise SystemExit("not a FeatureCollection with features")
    for f in features[:50]:
        if f["geometry"]["type"] != "Point":
            raise SystemExit("features must be Points")
        if not isinstance(f["properties"].get("h"), int):
            raise SystemExit("each feature needs an integer `h` (metres)")
    return len(features)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    n = validate(sys.argv[1])
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sys.argv[1], DEST)
    print(f"published {n} features -> {DEST}")


if __name__ == "__main__":
    main()
