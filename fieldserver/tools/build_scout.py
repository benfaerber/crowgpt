"""Build and publish the CawScout layer.

    uv run python tools/build_scout.py                    # all regions -> instance/scout.json
    uv run python tools/build_scout.py --region slc-valley
    uv run python tools/build_scout.py --out /tmp/scout.json   # build without publishing

The production successor to experiment 0084's script chain: fetches the
signals (iNaturalist, Overpass, eBird), scores each region in
fieldserver.scout.regions, assembles targets + owls + predators + icons +
rail, validates the shape the app depends on, and replaces
instance/scout.json, which /api/scout serves. Icons are carried forward
from the previous publish. No server restart needed — the endpoint reads
the file per request.

The file is replaced whole: once several regions exist, build them together
(the default) rather than one at a time, or the others vanish from the map.
"""

import argparse
import json
import sys
from pathlib import Path

FIELDSERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FIELDSERVER / "src"))

from fieldserver.scout import REGIONS, ScoutLayerBuilder, validate
from fieldserver.scout.regions import by_slug
from fieldserver.scout.sources import EBirdClient


def ebird_client():
    secrets = FIELDSERVER / "instance" / "secrets.env"
    if secrets.exists():
        for line in secrets.read_text().splitlines():
            line = line.strip().removeprefix("export ")
            if line.startswith("EBIRD_API_KEY="):
                return EBirdClient(line.split("=", 1)[1].strip('"').strip("'"))
    raise SystemExit("EBIRD_API_KEY not in fieldserver/instance/secrets.env")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", action="append", metavar="SLUG",
                        help="build only this region (repeatable); "
                             f"known: {[r.slug for r in REGIONS]}")
    parser.add_argument("--out", type=Path,
                        help="write here instead of publishing")
    args = parser.parse_args()

    regions = [by_slug(s) for s in args.region] if args.region else REGIONS
    dest = args.out or FIELDSERVER / "instance" / "scout.json"
    published = FIELDSERVER / "instance" / "scout.json"
    previous = json.loads(published.read_text()) if published.exists() else {}

    builder = ScoutLayerBuilder(
        repo_root=FIELDSERVER.parent,
        db_path=FIELDSERVER / "instance" / "field.db",
        ebird=ebird_client(),
        grid_dir=FIELDSERVER / "instance" / "scout_grid")
    layer = builder.build(regions, previous=previous)
    validate(layer)

    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(layer) + "\n")
    tmp.replace(dest)

    for t in layer["targets"][:10]:
        label = f" ({t['near']})" if t["near"] else ""
        print(f"#{t['rank']:2d} score {t['score']} at "
              f"{t['lat']},{t['lon']}{label}")
    print(f"{len(layer['targets'])} targets, {len(layer['owls'])} owls, "
          f"{len(layer['predators'])} predators, {len(layer['icons'])} icons, "
          f"{len(layer['rail'])} rail segments -> {dest}")


if __name__ == "__main__":
    main()
