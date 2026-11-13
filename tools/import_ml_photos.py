"""Import corvid photos from the Macaulay Library into data/photos.

Two inputs, both produced by a signed-in human in the web UI, because the
search endpoint answers scripts with a bot check:

- a **CSV export** of a media search (preferred). Rows carry the ML Catalog
  Number, so each photo is fetched from the media host by id at 480px, and
  the recordist, date and coordinates are kept for attribution and range
  priors. A random sample of `--limit` photo rows is taken, seeded, so a
  later run with a higher limit extends the same sample.
- a **saved search page**: Ctrl+S leaves a `<page>_files/` folder holding the
  grid thumbnails as `480_<n>_<suffix>.jpeg` beside CSS, logos and the
  spectrogram strips of audio results. Asset ids do not survive the rename;
  the species comes from the page title the folder is named after.

    python tools/import_ml_photos.py ~/Downloads/ML__2026-11-13T01-59_carcro1.csv --limit 400
    python tools/import_ml_photos.py "~/Downloads/American Crow - ... _files"

Writes `data/photos/macaulay/<slug>/<sha1>.jpg` and `data/photos/manifest.csv`.
Photos are named by content hash, so overlapping imports add only what is new.
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
ASSET_URL = "https://cdn.download.ams.birds.cornell.edu/api/v2/asset/{asset}/480"
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


class SavedSearchFolder:
    THUMBNAIL = re.compile(r"^480_.*\.(jpe?g|png)$", re.IGNORECASE)

    def __init__(self, path: Path):
        self.path = path
        self.slug = slugify(path.name.split(" - ")[0])

    def candidates(self, known_assets):
        return [Candidate(self.slug, p.name, p.read_bytes)
                for p in sorted(self.path.iterdir()) if self.THUMBNAIL.match(p.name)]


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
        time.sleep(PAUSE_SECONDS)
        request = urllib.request.Request(ASSET_URL.format(asset=asset), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            if not response.headers.get("Content-Type", "").startswith("image/"):
                raise RuntimeError(f"asset {asset}: media host answered {response.headers.get('Content-Type')}")
            return response.read()


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
    if path.suffix.lower() == ".csv":
        return CatalogueExport(path, limit)
    if path.is_dir():
        return SavedSearchFolder(path)
    sys.exit(f"Neither a CSV export nor a saved-page folder: {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--limit", type=int, default=400, help="photo rows to sample from each CSV")
    args = parser.parse_args()
    data_dir = Path(os.environ.get("DATA_DIR", REPO / "data"))
    library = PhotoLibrary(data_dir / "photos")
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
