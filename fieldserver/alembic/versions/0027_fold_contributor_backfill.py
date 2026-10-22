"""give pre-contributor devices their owners, then drop the columns that named them

The last schema/data coupling to move out of the stores. 0002 retired every
pre-contributor column it could and left `devices.contributor_name` and
`devices.is_operator` behind on purpose: the contributor backfill read them,
so the schema change could not precede the data change. The backfill lived in
ContributorStore and DeviceStore and ran at every startup; now data and drop
happen here, together, once.

Every step is conditional. The deployed database migrated long ago — no
orphan devices, no legacy columns — so this must be a no-op there rather
than an unnecessary table rebuild.

Revision ID: 0027_fold_contributor_backfill
Revises: 0026_engaged_ms
"""

import hashlib
import secrets
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0027_fold_contributor_backfill"
down_revision = "0026_engaged_ms"
branch_labels = None
depends_on = None

# Everything owned through a device. contributor_id on these is a column the
# earlier revisions create and a value only this backfill can fill, because it
# follows device_id through the contributor ids written below.
OWNED_TABLES = ("captures", "families", "labels", "observations",
                "context_events", "sightings")


def _columns(inspector, table):
    return {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "devices" not in tables:
        return
    present = _columns(inspector, "devices")
    named = "contributor_name" in present
    flagged = "is_operator" in present

    # One contributor *per orphaned device*, never one for all of them: this
    # runs unattended on whatever database it finds, and it cannot know
    # whether two device rows are one person with two phones or two people.
    # Preserving the existing ownership boundary is the only safe default —
    # merging is a deliberate act, and `tools/admin.py merge` is where it
    # lives. Both legacy columns may already be gone on a database that
    # migrated under the old store code, and naming a missing column is an
    # error even in a query that matches no rows, so look before selecting.
    columns = ", ".join(["id"]
                        + (["contributor_name"] if named else [])
                        + (["is_operator"] if flagged else []))
    orphans = bind.execute(sa.text(
        f"SELECT {columns} FROM devices "
        "WHERE contributor_id IS NULL ORDER BY id")).mappings().all()
    for device in orphans:
        name = ((device["contributor_name"] if named else None) or "").strip() \
            or "Unnamed recordist"
        role = "operator" if (flagged and device["is_operator"]) else "contributor"
        claim_hash = hashlib.sha256(
            secrets.token_urlsafe(9).encode()).hexdigest()
        made = bind.execute(sa.text(
            "INSERT INTO contributors (public_uuid, display_name, role, "
            "claim_code_hash, created_at) "
            "VALUES (:uuid, :name, :role, :hash, :now)"),
            {"uuid": secrets.token_hex(16), "name": name, "role": role,
             "hash": claim_hash,
             "now": datetime.now(timezone.utc).isoformat()})
        bind.execute(sa.text(
            "UPDATE devices SET contributor_id = :cid WHERE id = :id"),
            {"cid": made.lastrowid, "id": device["id"]})

    # Then the rows those devices made. Idempotent by the IS NULL guard, so an
    # owner corrected by hand is never overwritten.
    for table in OWNED_TABLES:
        if table not in tables:
            continue
        bind.execute(sa.text(
            f"UPDATE {table} SET contributor_id = "
            f"(SELECT d.contributor_id FROM devices d "
            f" WHERE d.id = {table}.device_id) "
            f"WHERE contributor_id IS NULL AND device_id IS NOT NULL"))

    # Only once every device has an owner: the backfill above was the last
    # reader of these columns. `is_operator` is the one worth dropping rather
    # than tolerating — authority lives on the contributor now, and a column
    # still sitting on the device looks settable while meaning nothing.
    if named or flagged:
        with op.batch_alter_table("devices") as batch:
            if flagged:
                batch.drop_column("is_operator")
            if named:
                batch.drop_column("contributor_name")


def downgrade() -> None:
    raise NotImplementedError("the pre-contributor columns were retired, not paused")
