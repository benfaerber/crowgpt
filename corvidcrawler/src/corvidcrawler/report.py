"""What a crawl is doing, on the terminal and in data/progress/.

An unattended crawl reports through crowgpt.progress.Run like every other
long job in this repo: the dashboard's Training panel lists
data/progress/*.json, and a crawl that only prints to a terminal is invisible
to the person it runs for. The module is stdlib-only and imported by path.
"""

import shutil
import sys
import time

from .config import REPO

sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402

#: How long an in-flight file may go without refreshing the JSON. The server
#: marks a run stale after 600 s, so a single slow download must not look hung.
REFRESH_SECONDS = 30.0


class CrawlReport:
    """One crawl, one stage: fetched/total on the line, downloaded and the
    bytes in flight beside it."""

    def __init__(self, title, step, tty=None):
        self.run = Run(title, [step])
        self.stage = self.run.stage(step)
        self.step = step
        self._tty = sys.stdout.isatty() if tty is None else tty
        self._last_line = ""
        self._last_write = time.monotonic()
        self._state = (0, 0, None)

    def __enter__(self):
        self.stage.__enter__()
        return self

    def __exit__(self, kind, value, tb):
        self.stage.__exit__(kind, value, tb)
        if self._tty and self._last_line:
            sys.stdout.write("\n")
            sys.stdout.flush()
        return False

    def update(self, fetched, downloaded, total=None, detail=""):
        self._state = (fetched, downloaded, total)
        self.stage.update(fetched, total, extra=self._extra(downloaded, detail))
        self._last_write = time.monotonic()
        self._draw(fetched, downloaded, total, detail)

    def in_flight(self, done_bytes, total_bytes):
        """Bytes of the file arriving now. The bar counts whole recordings, so
        without this a long file leaves the line byte-identical for minutes."""
        fetched, downloaded, total = self._state
        detail = (f"{done_bytes / 1e6:.0f}/{total_bytes / 1e6:.0f} MB" if total_bytes
                  else f"{done_bytes / 1e6:.0f} MB")
        if time.monotonic() - self._last_write > REFRESH_SECONDS:
            self.stage.update(fetched, total, extra=self._extra(downloaded, detail))
            self._last_write = time.monotonic()
        self._draw(fetched, downloaded, total, detail)

    def note(self, line):
        self.run.note(line)

    @staticmethod
    def _extra(downloaded, detail) -> str:
        return f"{downloaded} downloaded" + (f" · {detail}" if detail else "")

    @staticmethod
    def _bar(done, total, width=16) -> str:
        if not total:
            return "─" * width
        filled = int(width * min(1.0, done / total))
        return "█" * filled + "░" * (width - filled)

    def _draw(self, fetched, downloaded, total, detail):
        name = self.step if len(self.step) <= 18 else self.step[:17] + "…"
        line = (f"{name:<18} {self._bar(fetched, total)} {fetched}/{total or '?'} "
                f"· {self._extra(downloaded, detail)}")
        if self._tty:
            width = shutil.get_terminal_size((100, 20)).columns - 1
            sys.stdout.write("\r" + line[:width].ljust(len(self._last_line)))
            sys.stdout.flush()
            self._last_line = line[:width]
        elif line != self._last_line:
            print(line, flush=True)
            self._last_line = line
