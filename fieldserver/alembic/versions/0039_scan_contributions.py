"""scan_contributions — a visitor's upload, kept because they said it could be

Revision 0038 deletes a stranger's file the moment it has been read, and the
Scan page said so. Ben wants the uploads as data, so the page now carries an
unticked box, "Let CrowGPT keep this file", and a scan made with it ticked is
kept: the file moves to `instance/scan-contributions/` when the worker
finishes and a row here records what the scan said about it.

Only with the box ticked. `demo_scans.keep` carries the visitor's choice from
the upload to the worker; without it nothing changes and the file is deleted
as before. A failed scan is never kept, since a file no worker could read is
no data.

STILL NOT A CAPTURE. A contribution is an unreviewed file from a stranger
with a model's guess attached, so it stays out of the captures table and
every count over it until someone has looked at it. `latitude` and
`longitude` are what the visitor sent with the file (a city-level estimate),
and the result holds whatever the scan used. No address is stored.

`bytes` is there so the store can refuse to keep more than a fixed budget:
the route takes no token, and a box with a 40 GB disk should not be filled
by whoever finds the checkbox.

Revision ID: 0039_scan_contributions
Revises: 0038_demo_scans
"""

import sqlalchemy as sa
from alembic import op

revision = "0039_scan_contributions"
down_revision = "0038_demo_scans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "keep" not in {column["name"] for column in inspector.get_columns("demo_scans")}:
        op.add_column("demo_scans", sa.Column("keep", sa.Integer(), nullable=False, server_default="0"))
    if "scan_contributions" not in inspector.get_table_names():
        op.create_table(
            "scan_contributions",
            sa.Column("id", sa.Integer(), primary_key=True),
            # photo | audio | video
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("storage_ref", sa.Text(), nullable=False),
            sa.Column("bytes", sa.Integer(), nullable=False),
            sa.Column("latitude", sa.Float()),
            sa.Column("longitude", sa.Float()),
            sa.Column("result", sa.Text()),
            sa.Column("created_at", sa.Text(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("scan_contributions")
    with op.batch_alter_table("demo_scans") as batch:
        batch.drop_column("keep")
