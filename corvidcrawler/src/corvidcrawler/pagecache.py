"""Paged search results on disk, so a second run costs no API calls.

Results are written as the pages arrive, alongside the cursor that produced
them, so an interrupted crawl resumes where it stopped instead of paging the
whole query again. A cursor file written empty means the last page said there
was no next one.
"""

import json
from pathlib import Path


class PageCache:
    def __init__(self, root, subdir, name):
        self.dir = Path(root) / subdir
        self.items_path = self.dir / f"{name}.jsonl"
        self.cursor_path = self.dir / f"{name}.cursor"

    def read(self):
        if not self.items_path.exists():
            return
        with open(self.items_path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def append(self, items, cursor):
        self.dir.mkdir(parents=True, exist_ok=True)
        with open(self.items_path, "a", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item) + "\n")
        self.cursor_path.write_text(cursor or "")

    @property
    def cursor(self):
        return self.cursor_path.read_text().strip() if self.cursor_path.exists() else None

    @property
    def exhausted(self) -> bool:
        return self.cursor_path.exists() and not self.cursor_path.read_text().strip()

    def clear(self):
        self.items_path.unlink(missing_ok=True)
        self.cursor_path.unlink(missing_ok=True)
