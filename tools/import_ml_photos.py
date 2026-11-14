"""Import corvid photos from the Macaulay Library into data/photos.

The input is a CSV export of a Macaulay media search, made by a signed-in
human in the web UI because the search endpoint answers scripts with a bot
check. Rows carry the ML Catalog Number, so each photo is fetched from the
media host by id at 480px, with the recordist, date and coordinates kept for
attribution and range priors. A seeded random sample of `--limit` photo rows
is taken, so a re-run fetches the same photos and a higher limit extends the
same sample.

    make photos     # every CSV in data/photos/macaulay-exports
    python tools/import_ml_photos.py path/to/ML__..._carcro1.csv --limit 400

Writes `data/photos/macaulay/<slug>/<sha1>.jpg` and `data/photos/manifest.csv`.
Photos are named by content hash, so overlapping imports add only what is new.

`--large` then fetches the 1200px version of every photo in the manifest into
`data/photos/macaulay-1200/<catalog number>.jpg`. The photo classifier crops
the bird out of these, and 480px leaves too little of a small bird.
"""

import argparse
import csv
import hashlib
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

FIELDS = ("sha1", "slug", "source", "path", "original_name",
          "asset_id", "recordist", "date", "latitude", "longitude", "rating")
ASSET_URL = "https://cdn.download.ams.birds.cornell.edu/api/v2/asset/{asset}/{size}"
THUMBNAIL_SIZE = 480
LARGE_SIZE = 1200
USER_AGENT = "crowgpt-photo-import/1.0"
PAUSE_SECONDS = 0.5
SEED = 90


def slugify(common_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", common_name.lower()).strip("-")


class Candidate:
    def __init__(self, slug, original_name, read_bytes, **metadata):
        self.slug = slug
        self.original_name = original_name
        self.read_bytes = read_bytes
        self.metadata = metadata


class CatalogueExport:
    def __init__(self, path: Path, limit: int):
        self.path = path
        self.limit = limit

    def _photo_rows(self):
        with open(self.path, newline="", encoding="utf-8-sig") as handle:
            rows = [r for r in csv.DictReader(handle) if r.get("Format") == "Photo"]
        if not rows:
            sys.exit(f"{self.path} has no Photo rows — is it a Macaulay export?")
        random.Random(SEED).shuffle(rows)
        return rows[:self.limit]

    def candidates(self, known_assets):
        return [self._candidate(row) for row in self._photo_rows()
                if row["ML Catalog Number"] not in known_assets]

    def _candidate(self, row):
        asset = row["ML Catalog Number"]
        return Candidate(
            slugify(re.sub(r"\s*\(.*\)", "", row["Common Name"])),
            f"ML{asset}",
            lambda asset=asset: self._fetch(asset),
            asset_id=asset,
            recordist=row["Recordist"],
            date=row["Date"],
            latitude=row["Latitude"],
            longitude=row["Longitude"],
            rating=row["Average Community Rating"],
        )

    @staticmethod
    def _fetch(asset):
        return MediaHost.fetch(asset, THUMBNAIL_SIZE)


class MediaHost:
    @staticmethod
    def fetch(asset, size):
        time.sleep(PAUSE_SECONDS)
        url = ASSET_URL.format(asset=asset, size=size)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            if not response.headers.get("Content-Type", "").startswith("image/"):
                raise RuntimeError(f"asset {asset}: media host answered {response.headers.get('Content-Type')}")
            return response.read()


class LargePhotos:
    def __init__(self, library):
        self.root = library.root / f"macaulay-{LARGE_SIZE}"
        self.assets = sorted(library.known_assets())

    def missing(self):
        return [a for a in self.assets if not (self.root / f"{a}.jpg").exists()]

    def fetch(self, on_progress) -> dict:
        self.root.mkdir(parents=True, exist_ok=True)
        todo = self.missing()
        tally = {"added": 0, "failed": 0}
        for count, asset in enumerate(todo, 1):
            on_progress(count, len(todo))
            try:
                (self.root / f"{asset}.jpg").write_bytes(MediaHost.fetch(asset, LARGE_SIZE))
                tally["added"] += 1
            except (OSError, RuntimeError, urllib.error.URLError) as error:
                print(f"ML{asset}: {error}", file=sys.stderr)
                tally["failed"] += 1
        return tally


class PhotoLibrary:
    SOURCE = "macaulay"

    def __init__(self, root: Path):
        self.root = root
        self.manifest_path = root / "manifest.csv"
        self.rows = self._read_manifest()

    def _read_manifest(self) -> dict[str, dict]:
        if not self.manifest_path.exists():
            return {}
        with open(self.manifest_path, newline="") as handle:
            return {row["sha1"]: row for row in csv.DictReader(handle)}

    def known_assets(self) -> set[str]:
        return {row["asset_id"] for row in self.rows.values() if row.get("asset_id")}

    def add(self, candidates, on_progress) -> dict:
        tally = {"added": 0, "duplicate": 0, "failed": 0}
        for count, candidate in enumerate(candidates, 1):
            on_progress(count, candidate.slug)
            try:
                content = candidate.read_bytes()
            except (OSError, RuntimeError, urllib.error.URLError) as error:
                print(f"{candidate.original_name}: {error}", file=sys.stderr)
                tally["failed"] += 1
                continue
            digest = hashlib.sha1(content).hexdigest()
            if digest in self.rows:
                tally["duplicate"] += 1
                continue
            destination = self.root / self.SOURCE / candidate.slug / f"{digest}.jpg"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            self.rows[digest] = {
                "sha1": digest,
                "slug": candidate.slug,
                "source": self.SOURCE,
                "path": str(destination.relative_to(self.root)),
                "original_name": candidate.original_name,
                **candidate.metadata,
            }
            tally["added"] += 1
            if count % 50 == 0:
                self.save()
        self.save()
        return tally

    def save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, restval="")
            writer.writeheader()
            writer.writerows(self.rows.values())



def open_source(path: Path, limit: int):
    if path.suffix.lower() != ".csv":
        sys.exit(f"Not a CSV export: {path}")
    return CatalogueExport(path, limit)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("--limit", type=int, default=400, help="photo rows to sample from each CSV")
    parser.add_argument("--large", action="store_true", help="also fetch the 1200px version of every photo")
    args = parser.parse_args()
    data_dir = Path(os.environ.get("DATA_DIR", REPO / "data"))
    library = PhotoLibrary(data_dir / "photos")
    if args.inputs:
        import_thumbnails(library, args)
    if args.large:
        fetch_large(library)


def fetch_large(library):
    run = Run("MACAULAY LARGE PHOTOS", ["fetch"])
    with run.stage("fetch") as stage:
        tally = LargePhotos(library).fetch(lambda n, total: stage.update(n, total) if n % 5 == 1 else None)
        line = f"1200px photos: {tally['added']} added, {tally['failed']} failed"
        print(line)
        run.note(line)
        stage.update(1, 1)


def import_thumbnails(library, args):
    known = library.known_assets()
    batches = [(path, open_source(path.expanduser(), args.limit).candidates(known)) for path in args.inputs]
    total = sum(len(candidates) for _, candidates in batches)
    run = Run("MACAULAY PHOTO IMPORT", ["import"])
    with run.stage("import") as stage:
        offset = 0
        for path, candidates in batches:
            tally = library.add(
                candidates,
                lambda n, slug: stage.update(offset + n, total, extra=slug) if n % 5 == 1 else None,
            )
            offset += len(candidates)
            line = f"{path.name}: {tally['added']} added, {tally['duplicate']} already present, {tally['failed']} failed"
            print(line)
            run.note(line)
        stage.update(total, total)


if __name__ == "__main__":
    main()
