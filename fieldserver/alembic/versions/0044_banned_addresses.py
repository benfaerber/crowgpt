"""banned addresses — addresses the public forms no longer take anything from

The access form was flooded on 2026-11-19 by scripts posting other people's
emails from a handful of addresses. The hourly allowance slows a flood and
forgets it on restart; a ban is the operator saying "never from here", and it
has to outlive the process. One row per address, exact match.

Revision ID: 0044_banned_addresses
Revises: 0043_scan_addresses
"""

import sqlalchemy as sa
from alembic import op

revision = "0044_banned_addresses"
down_revision = "0043_scan_addresses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "banned_addresses" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "banned_addresses",
        sa.Column("ip", sa.Text(), primary_key=True),
        sa.Column("banned_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("banned_addresses")
