"""retire the columns the contributor layer replaced, and pin two NOT NULLs

The first real migration, and the one that shows why this was worth adopting.

Three shapes here cannot be reached with ALTER TABLE, which is why they were
never fixed: `captures.keep` and `devices.locale` are nullable on databases old
enough to predate their defaults, and `captures.sighting_id` is a column from an
abandoned design. Dropping a column and tightening a constraint both require
rewriting the table, and SQLite has no syntax for either — `batch_alter_table`
does the rewrite.

`devices.contributor_name` and `devices.is_operator` stay with the store for
now: the contributor backfill reads them, so the schema change cannot precede
the data change. Moving both here together is the next step, not this one.

Every step is conditional: the deployed database already has the right shape, so
this must be a no-op there rather than an unnecessary table rebuild.

Revision ID: 0002_retire_pre_contributor
Revises: 0001_baseline
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_retire_pre_contributor"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

# table -> columns that no longer exist.
#
# `devices.contributor_name` and `devices.is_operator` are deliberately absent:
# ContributorStore.backfill_from_devices() reads them to build the contributor
# rows, so dropping them here would run before the data that depends on them had
# moved. Schema and data migration are coupled in that one case, and until the
# backfill itself lives in a revision, the store keeps that drop.
RETIRED = {
    "captures": ["sighting_id"],
}

# table -> (column, type, default) that should never have been nullable
TIGHTEN = [
    ("captures", "keep", sa.Integer(), "0"),
    ("devices", "locale", sa.Text(), "'en'"),
]


def _columns(inspector, table):
    return {c["name"]: c for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    for table, columns in RETIRED.items():
        if table not in tables:
            continue
        present = [c for c in columns if c in _columns(inspector, table)]
        if not present:
            continue
        with op.batch_alter_table(table) as batch:
            for column in present:
                batch.drop_column(column)

    inspector = sa.inspect(bind)
    for table, column, kind, default in TIGHTEN:
        if table not in tables:
            continue
        found = _columns(inspector, table).get(column)
        if found is None or not found["nullable"]:
            continue
        # A row already holding NULL would fail the new constraint, so it is
        # given the default the column should always have had.
        op.execute(f"UPDATE {table} SET {column} = {default} WHERE {column} IS NULL")
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, existing_type=kind, nullable=False,
                               server_default=sa.text(default))


def downgrade() -> None:
    raise NotImplementedError("these columns were retired, not paused")
