"""The schema is what the migrations say it is, and drift is detectable.

Written because "the table exists" and "the table is the right shape" turned out
to be different questions, and only the first was ever being asked.
`context_events.label_uuid NOT NULL` survived weeks of installs by being present
and wrong.
"""

import sqlite3

import pytest

from fieldserver.core import schema
from fieldserver.app import create_app


class TestDrift:

    def test_a_migrated_database_has_none(self, db_path):
        create_app(db_path)
        assert schema.drift(db_path) == []

    def test_a_missing_column_is_reported(self, db_path, tmp_path):
        create_app(db_path)
        # SQLite cannot drop a column without a rebuild, so a table is
        # substituted — which is also what a half-applied migration leaves.
        with sqlite3.connect(db_path) as conn:
            conn.execute("ALTER TABLE captures RENAME TO captures_old")
            conn.execute("CREATE TABLE captures (id INTEGER PRIMARY KEY, status TEXT)")
        problems = schema.drift(db_path)
        assert any("captures.keep: column missing" in p for p in problems)

    def test_a_wrong_nullability_is_reported(self, db_path):
        # The exact shape of the bug this exists for: the column is there, the
        # code is happy, and every insert without it fails at runtime.
        create_app(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute("ALTER TABLE context_events RENAME TO ce_old")
            conn.execute(
                "CREATE TABLE context_events (id INTEGER PRIMARY KEY, "
                "capture_id INTEGER NOT NULL, label_id INTEGER NOT NULL, "
                "key TEXT NOT NULL, created_at TEXT NOT NULL)")
        problems = schema.drift(db_path)
        assert any("context_events.label_id: is NOT NULL, should be nullable" in p
                   for p in problems)

    def test_an_unexpected_table_is_reported_not_ignored(self, db_path):
        # A leftover from a half-finished rebuild looks like nothing at all
        # until something queries it.
        create_app(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE captures_rebuilt (id INTEGER PRIMARY KEY)")
        assert any("captures_rebuilt" in p for p in schema.drift(db_path))

    def test_the_alembic_ledger_is_not_itself_drift(self, db_path):
        # alembic_version is bookkeeping *about* the schema, not part of it.
        create_app(db_path)
        assert "alembic_version" not in str(schema.drift(db_path))


class TestStartupRefuses:

    def test_a_wrong_shape_stops_the_server(self, db_path):
        create_app(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute("ALTER TABLE labels RENAME TO labels_old")
            conn.execute("CREATE TABLE labels (id INTEGER PRIMARY KEY)")
        # Serving would accept writes and silently drop the fields it does not
        # recognise, which is how a sync reports success while losing data.
        with pytest.raises(RuntimeError, match="does not match the migrations"):
            create_app(db_path)

    def test_the_message_names_the_fix(self, db_path):
        create_app(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.execute("ALTER TABLE labels RENAME TO labels_old")
            conn.execute("CREATE TABLE labels (id INTEGER PRIMARY KEY)")
        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            create_app(db_path)


class TestMigrationsBuildTheSchema:

    def test_a_brand_new_database_needs_no_store_help(self, tmp_path):
        # Every table comes from the migrations. If a store were still creating
        # one, removing it from the baseline would go unnoticed until a fresh
        # deployment.
        fresh = tmp_path / "new.db"
        schema.upgrade(fresh)
        assert set(schema.shape(fresh)) == set(schema.reference_shape())

    def test_it_is_recorded_as_migrated(self, tmp_path):
        fresh = tmp_path / "new.db"
        schema.upgrade(fresh)
        with sqlite3.connect(fresh) as conn:
            assert conn.execute("SELECT version_num FROM alembic_version").fetchone()
