"""Where the database is, resolved the same way everywhere.

The path was worked out independently in app.py, in the worker and in the
Makefile. Alembic needs it too, and a fourth copy is how a migration gets run
against a different file from the one being served.
"""

import os
from pathlib import Path

# fieldserver/core/paths.py → src/fieldserver/core → src/fieldserver → src →
# the project. Counted from the package rather than from this file's depth, so
# moving a module between folders cannot silently point the migrations at a
# directory that does not exist — which is exactly what it did.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = PROJECT_ROOT / "instance" / "field.db"


def database_path(explicit: Path | str | None = None) -> Path:
    return Path(explicit or os.environ.get("FIELD_DB") or DEFAULT_DB)


def database_url(explicit: Path | str | None = None) -> str:
    return f"sqlite+pysqlite:///{database_path(explicit)}"
