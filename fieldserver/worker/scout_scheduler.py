"""Rebuild the CawScout layer once a week, visibly.

This is the field server's cron: it rides the `make field` stack like the
other workers, checks the published layer's age every 15 minutes, and
reruns tools/build_scout.py when it crosses REBUILD_AFTER_S. The layer's
own mtime is the schedule — no state file to drift, and a laptop that
slept through Tuesday simply builds when it wakes. A manual `make scout`
resets the week by existing.

Reports through crowgpt.progress.Run (the dashboard's Training panel), so
an overnight rebuild that dies says why on a card instead of just being
stale. A failed attempt waits RETRY_AFTER_S rather than hammering the
public APIs every 15 minutes.
"""

import subprocess
import sys
import time
from pathlib import Path

FIELDSERVER = Path(__file__).resolve().parents[1]
REPO = FIELDSERVER.parent
sys.path.insert(0, str(REPO / "crowgpt" / "src"))
from crowgpt.progress import Run  # noqa: E402  (stdlib-only module)

SCOUT_JSON = FIELDSERVER / "instance" / "scout.json"
REBUILD_AFTER_S = 7 * 24 * 3600
CHECK_EVERY_S = 15 * 60
RETRY_AFTER_S = 6 * 3600


def age_s(path=SCOUT_JSON, now=None):
    """Seconds since the layer was last published; infinite when never."""
    if not path.exists():
        return float("inf")
    return (now or time.time()) - path.stat().st_mtime


def rebuild():
    run = Run("weekly scout rebuild", ["rebuild"])
    with run.stage("rebuild") as stage:
        process = subprocess.Popen(
            ["uv", "run", "python", "tools/build_scout.py"],
            cwd=FIELDSERVER, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        lines = 0
        for line in process.stdout:
            lines += 1
            # Every build line refreshes the stale clock; the last one is
            # the card's live caption.
            stage.update(lines, extra=line.strip()[:120])
        if process.wait() != 0:
            raise RuntimeError(f"build_scout.py exited {process.returncode}")
    run.note(f"published {SCOUT_JSON.name}, "
             f"next rebuild in {REBUILD_AFTER_S // 86400} days")


def main():
    print(f"scout scheduler up — rebuilds when {SCOUT_JSON.name} turns "
          f"{REBUILD_AFTER_S // 86400} days old", flush=True)
    while True:
        if age_s() > REBUILD_AFTER_S:
            try:
                rebuild()
            except Exception as error:  # Run already carries the traceback
                print(f"rebuild failed, retrying in "
                      f"{RETRY_AFTER_S // 3600}h: {error}", flush=True)
                time.sleep(RETRY_AFTER_S)
                continue
        time.sleep(CHECK_EVERY_S)


if __name__ == "__main__":
    main()
