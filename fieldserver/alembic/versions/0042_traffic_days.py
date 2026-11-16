"""traffic days — crowgpt.org's Cloudflare traffic, one summary per UTC day

Cloudflare's free plan keeps eight days, so a week nobody pulled was gone. The
traffic worker now writes each day here: today provisionally, every hour, and a
finished day once more with `final` set. `summary` is the JSON the dashboard's
Traffic page reads; it carries counts only, never a visitor's IP.

Revision ID: 0042_traffic_days
Revises: 0041_scan_desk
"""

import sqlalchemy as sa
from alembic import op

revision = "0042_traffic_days"
down_revision = "0041_scan_desk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "traffic_days" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "traffic_days",
        sa.Column("day", sa.Text(), primary_key=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("final", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("traffic_days")
