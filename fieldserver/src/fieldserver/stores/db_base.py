import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Shared SQLite connection handling for the field server's stores.

    Every store points at the same database file, so captures, media, labels,
    devices, and the served config all live together in one instance file —
    one file, one store per table.
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        """A connection tuned for two writers on one file.

        The API server and the BirdNET worker hold this database open at the
        same time, so the defaults are wrong in two ways. Rollback-journal mode
        lets a reader block a writer, which turns "a job finished while a phone
        was uploading" into `database is locked`; WAL lets them run side by
        side. And a writer that does have to wait needs to be told to wait —
        without `busy_timeout` SQLite gives up immediately rather than
        retrying. WAL is a property of the file, so it sticks after the first
        connection; the timeout is per-connection and has to be set every time.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

