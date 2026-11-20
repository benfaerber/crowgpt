"""scan addresses — a scan remembers the address it was uploaded from

The Scan page takes a file from anyone, and until now the server knew nothing
about who: the address fed the hourly allowance in memory and was gone. That
left no way to tell one person's forty uploads from forty people's, or to
connect a kept file to the flood it arrived in. `demo_scans.requester_ip` is
the address for the hour the row lives; `scan_contributions.requester_ip`
carries it over when the visitor lets the project keep the file. Only the
operator's routes return either. The Scan page says so.

Revision ID: 0043_scan_addresses
Revises: 0042_traffic_days
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_scan_addresses"
down_revision = "0042_traffic_days"
branch_labels = None
depends_on = None

TABLES = ("demo_scans", "scan_contributions")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table in TABLES:
        if "requester_ip" not in {column["name"] for column in inspector.get_columns(table)}:
            op.add_column(table, sa.Column("requester_ip", sa.Text()))


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("requester_ip")
