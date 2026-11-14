"""Photo worker — answers the dashboard's Photo ID page.

Polls `photo_identifications`, names the corvid in each uploaded photo with
analyzer/photo, and writes the ranking back. The shared SQLite DB is the only
coupling to the API, as it is for the other workers.

Runs under analyzer/photo's venv: BioCLIP and the bird detector are torch, and
no other venv here carries torchvision or open_clip. The models load on the
first photo, not at startup, and are dropped after an idle spell, because
together they hold a couple of gigabytes and most hours nobody uploads one.

  ../analyzer/photo/.venv/bin/python worker/photo_worker.py
  # one pass then exit (cron / test):   ... worker/photo_worker.py --once
  # against a specific DB:              FIELD_DB=/path/field.db
  # hold the models longer:             PHOTO_ID_IDLE_MINUTES=60
"""

import gc
import os
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDSERVER = HERE.parent
REPO = FIELDSERVER.parent
sys.path.insert(0, str(FIELDSERVER / "src"))
sys.path.insert(0, str(REPO))

from fieldserver.stores.photo_ids import PhotoIdStore  # noqa: E402

DEFAULT_DB = FIELDSERVER / "instance" / "field.db"
IDLE_MINUTES = float(os.environ.get("PHOTO_ID_IDLE_MINUTES", "10"))
POLL_SECONDS = float(os.environ.get("PHOTO_ID_POLL_SECONDS", "1"))


class LazyIdentifier:
    """The classifier, loaded when first needed and let go when idle."""

    def __init__(self, idle_minutes=IDLE_MINUTES):
        self.idle_seconds = idle_minutes * 60
        self.identifier = None
        self.last_used = 0.0

    def identify(self, path, latitude, longitude):
        if self.identifier is None:
            from analyzer.photo import PhotoIdentifier

            print("[photo] loading the classifier", flush=True)
            self.identifier = PhotoIdentifier.load()
        self.last_used = time.monotonic()
        return self.identifier.identify(path, latitude, longitude)

    def release_if_idle(self) -> bool:
        if self.identifier is None or time.monotonic() - self.last_used < self.idle_seconds:
            return False
        self.identifier = None
        gc.collect()
        print("[photo] idle, classifier released", flush=True)
        return True


def process(job, store, identifier):
    """One photo, start to finish. Any failure lands in the row, so the page
    shows why instead of a spinner that never ends."""
    try:
        result = identifier.identify(store.path(job), job["latitude"], job["longitude"])
        return store.complete(job["id"], result.to_dict())
    except Exception as error:  # noqa: BLE001 — the row is the only place this is read
        return store.fail(job["id"], f"{type(error).__name__}: {error}")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    once = "--once" in argv
    db_path = Path(os.environ.get("FIELD_DB") or DEFAULT_DB)
    store = PhotoIdStore(db_path, db_path.parent / "photo-id")
    # `make field` starts this beside the server, whose migrations create the
    # table. On a fresh schema it is not there for a few seconds: wait for it.
    while True:
        try:
            requeued, abandoned = store.reclaim_running()
            break
        except sqlite3.OperationalError as error:
            if "no such table" not in str(error) or once:
                raise
            print("[photo] waiting for the server's migration", flush=True)
            time.sleep(POLL_SECONDS)
    if requeued or abandoned:
        print(f"[photo] startup: {requeued} requeued, {abandoned} abandoned", flush=True)
    identifier = LazyIdentifier()
    print(f"[photo] watching {db_path}", flush=True)
    while True:
        try:
            job = store.claim_next()
        except sqlite3.OperationalError as error:
            if once:
                raise
            print(f"[photo] poll failed, retrying: {error}", flush=True)
            time.sleep(POLL_SECONDS)
            continue
        if job is None:
            if once:
                return 0
            identifier.release_if_idle()
            time.sleep(POLL_SECONDS)
            continue
        started = time.monotonic()
        row = process(job, store, identifier)
        outcome = row["state"] if row else "forgotten"
        print(f"[photo] #{job['id']} {outcome} in {time.monotonic() - started:.1f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
