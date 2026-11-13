"""Import photo thumbnails from a saved Macaulay Library search page.

Saving the media search with Ctrl+S leaves a `<page>_files/` folder holding
every grid thumbnail as `480_<n>_<suffix>.jpeg`, beside the site's CSS, logos
and the 2500px-wide spectrogram strips of any audio results (`preview_*`).
The browser renames each file, so asset ids do not survive; the species comes
from the page title the folder is named after.

    python tools/import_ml_photos.py "~/Downloads/American Crow - ... _files"

Writes `data/photos/macaulay/<slug>/<sha1>.<ext>` and appends to
`data/photos/manifest.csv`. Re-importing a folder, or a second dump that
overlaps the first, adds only photos not already there.
"""

import argparse
import csv
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIELDS = ("sha1", "slug", "source", "path", "original_name")


class SavedSearchFolder:
    THUMBNAIL = re.compile(r"^480_.*\.(jpe?g|png)$", re.IGNORECASE)

    def __init__(self, path: Path):
        self.path = path

    @property
    def slug(self) -> str:
        common_name = self.path.name.split(" - ")[0]
        return re.sub(r"[^a-z0-9]+", "-", common_name.lower()).strip("-")

    def thumbnails(self) -> list[Path]:
        return sorted(p for p in self.path.iterdir() if self.THUMBNAIL.match(p.name))


class PhotoLibrary:
    SOURCE = "macaulay"

    def __init__(self, root: Path):
        self.root = root
        self.manifest_path = root / "manifest.csv"
        self.known = self._read_manifest()

    def _read_manifest(self) -> dict[str, dict]:
        if not self.manifest_path.exists():
            return {}
        with open(self.manifest_path, newline="") as handle:
            return {row["sha1"]: row for row in csv.DictReader(handle)}

    def add(self, folder: SavedSearchFolder) -> tuple[int, int]:
        target = self.root / self.SOURCE / folder.slug
        target.mkdir(parents=True, exist_ok=True)
        added, skipped = [], 0
        for photo in folder.thumbnails():
            digest = hashlib.sha1(photo.read_bytes()).hexdigest()
            if digest in self.known:
                skipped += 1
                continue
            destination = target / f"{digest}{photo.suffix.lower().replace('.jpeg', '.jpg')}"
            shutil.copyfile(photo, destination)
            row = {
                "sha1": digest,
                "slug": folder.slug,
                "source": self.SOURCE,
                "path": str(destination.relative_to(self.root)),
                "original_name": photo.name,
            }
            self.known[digest] = row
            added.append(row)
        self._append(added)
        return len(added), skipped

    def _append(self, rows: list[dict]):
        fresh = not self.manifest_path.exists()
        with open(self.manifest_path, "a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            if fresh:
                writer.writeheader()
            writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folders", nargs="+", type=Path)
    args = parser.parse_args()
    data_dir = Path(os.environ.get("DATA_DIR", REPO / "data"))
    library = PhotoLibrary(data_dir / "photos")
    for path in args.folders:
        folder = SavedSearchFolder(path.expanduser())
        if not folder.path.is_dir():
            sys.exit(f"Not a folder: {folder.path}")
        added, skipped = library.add(folder)
        print(f"{folder.slug}: {added} added, {skipped} already present")


if __name__ == "__main__":
    main()
