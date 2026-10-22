"""Finding the audio an experiment refers to.

Captures are named by their server id, because that is how they are discussed
("capture 88") and how the dashboard shows them. The mapping from id to file
lives in the database, so it is read rather than hardcoded — storage_ref is a
random hex name that means nothing on its own.
"""

import os
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MEDIA = REPO / "fieldserver" / "instance" / "media"
DEFAULT_DB = REPO / "fieldserver" / "instance" / "field.db"


def media_dir() -> Path:
    return Path(os.environ.get("FIELD_MEDIA", DEFAULT_MEDIA))


def field_db() -> Path:
    """The database experiments read, honouring FIELD_DB like audio_for does.

    Two experiments hardcoded their own copy of the default path and so
    resolved audio against one database and detections against another the
    moment FIELD_DB was set.
    """
    return Path(os.environ.get("FIELD_DB", DEFAULT_DB))


def audio_for(capture_id: int) -> Path:
    """The stored audio for a capture, by its server id."""
    db = field_db()
    with sqlite3.connect(str(db)) as conn:
        row = conn.execute(
            "SELECT storage_ref FROM media WHERE capture_id = ? AND kind = 'audio' "
            "AND upload_state = 'complete' ORDER BY id DESC LIMIT 1",
            (capture_id,)).fetchone()
    if not row:
        raise SystemExit(f"no complete audio for capture {capture_id} in {db}")
    path = media_dir() / row[0]
    if not path.exists():
        raise SystemExit(f"{path} is missing — set FIELD_MEDIA?")
    return path
