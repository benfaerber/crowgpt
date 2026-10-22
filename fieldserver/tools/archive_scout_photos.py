"""Archive the scout layer's sighting photos server-side, for the record.

The phone loads photos straight from iNat's CDN (the field server is
home-LAN only and unreachable on a cellular walk), so this cache serves no
request path today. It exists because observations get deleted and URLs
rot: one copy of each photo, fetched once, kept beside the database. Rerun
after each layer rebuild; already-archived photos are skipped.
"""
import json
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LAYER = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    REPO / "fieldserver" / "instance" / "scout.json"
OUT = REPO / "fieldserver" / "instance" / "scout-photos"


def main():
    OUT.mkdir(exist_ok=True)
    layer = json.loads(LAYER.read_text())
    fetched = skipped = failed = 0
    for sighting in layer.get("predators", []):
        url = sighting.get("photo")
        if not url:
            continue
        name = url.split("/photos/")[-1].split("/")[0]
        suffix = Path(url.split("?")[0]).suffix or ".jpg"
        target = OUT / f"{name}{suffix}"
        if target.exists():
            skipped += 1
            continue
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "cawtalker-archive"})
            with urllib.request.urlopen(request, timeout=30) as response:
                target.write_bytes(response.read())
            fetched += 1
        except Exception as failure:
            failed += 1
            print(f"failed: {url} ({failure})")
    print(f"{fetched} archived, {skipped} already held, {failed} failed "
          f"-> {OUT}")


if __name__ == "__main__":
    main()
