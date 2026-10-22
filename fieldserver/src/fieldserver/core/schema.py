"""Bringing a database up to head, and checking that it got there.

Two separate questions, and today taught us they are separate. Alembic answers
"has every migration run?" — a version string. This module also answers "is the
database actually the right shape?", which is different: a table can exist,
claim to be current, and carry a constraint nobody intended. That is exactly how
`context_events.label_uuid NOT NULL` survived for weeks, invisible until a tag
would not save.

The reference shape is not declared anywhere. It is read from a throwaway
database built by running the migrations, so there is nothing to keep in sync
with anything — the check compares the live database against what a fresh one
would be, which is the only definition of "right" that cannot itself drift.
"""

import sqlite3
import tempfile
from functools import lru_cache
from pathlib import Path

from alembic import command
from alembic.config import Config

from .paths import PROJECT_ROOT, database_path

ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


def _config(db_path: Path) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite+pysqlite:///{db_path}")
    return config


def upgrade(db_path: Path | str | None = None) -> None:
    """Run every migration this database has not applied yet."""
    resolved = database_path(db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(_config(resolved), "head")


def upgrade_to(db_path: Path | str, revision: str) -> None:
    """Migrate only as far as `revision`.

    For tests that need a database as it stood before some change, so a
    migration can be exercised against the shape it was written for rather than
    against the one it already produced.
    """
    resolved = database_path(db_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(_config(resolved), revision)


def stamp(db_path: Path | str | None = None, revision: str = "head") -> None:
    """Record a database as already at `revision` without running anything.

    For adopting a database whose schema predates Alembic — verified equivalent
    first, or this is just a lie written down.
    """
    command.stamp(_config(database_path(db_path)), revision)


def shape(db_path: Path | str) -> dict[str, dict[str, tuple]]:
    """Every table's columns, with type, nullability and default.

    Alembic's own version table is excluded: it is bookkeeping about the schema
    rather than part of it.
    """
    out: dict[str, dict[str, tuple]] = {}
    with sqlite3.connect(str(db_path)) as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' ORDER BY name")]
        for table in tables:
            out[table] = {
                row[1]: (row[2], row[3], row[4], row[5])
                for row in conn.execute(f"PRAGMA table_info({table})")
            }
    return out


@lru_cache(maxsize=1)
def reference_shape() -> dict[str, dict[str, tuple]]:
    """What a database built from the migrations looks like, right now.

    Cached for the life of the process: the migrations cannot change while it
    runs, and building this means running every one of them into a throwaway
    file. Uncached it was doing that on every create_app, which turned the test
    suite from ten seconds into eighty.
    """
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp) / "reference.db"
        upgrade(fresh)
        return shape(fresh)


def drift(db_path: Path | str | None = None) -> list[str]:
    """How the live database differs from a freshly migrated one.

    Empty means they agree. Each entry is one human-readable difference, phrased
    so it can go straight into an error message — the point is that somebody
    reads it, not that a program branches on it.
    """
    live = shape(database_path(db_path))
    reference = reference_shape()
    problems: list[str] = []

    for table in sorted(set(reference) - set(live)):
        problems.append(f"{table}: table missing")
    for table in sorted(set(live) - set(reference)):
        problems.append(f"{table}: table not in the migrations (left over?)")

    for table in sorted(set(reference) & set(live)):
        want, have = reference[table], live[table]
        for column in sorted(set(want) - set(have)):
            problems.append(f"{table}.{column}: column missing")
        for column in sorted(set(have) - set(want)):
            problems.append(f"{table}.{column}: column not in the migrations")
        for column in sorted(set(want) & set(have)):
            if want[column] == have[column]:
                continue
            kind, notnull, default = 0, 1, 2
            if want[column][notnull] != have[column][notnull]:
                expected = "NOT NULL" if want[column][notnull] else "nullable"
                actual = "NOT NULL" if have[column][notnull] else "nullable"
                problems.append(f"{table}.{column}: is {actual}, should be {expected}")
            elif want[column][kind] != have[column][kind]:
                problems.append(
                    f"{table}.{column}: is {have[column][kind]}, "
                    f"should be {want[column][kind]}")
            else:
                problems.append(
                    f"{table}.{column}: default is {have[column][default]!r}, "
                    f"should be {want[column][default]!r}")
    return problems
