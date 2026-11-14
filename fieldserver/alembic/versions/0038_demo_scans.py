"""demo_scans and worker_heartbeats — a stranger's upload to the promo's Scan page

crowgpt.org gets a page where a visitor uploads a photo, a recording or a
video and the hosted server says what is in it: the photo classifier names the
corvid, the BirdNET worker lays the calls out on a timeline. Each row of
demo_scans is one such upload and its answer.

NOT A CAPTURE, AND NEVER NEAR ONE. A stranger's file must not reach the
corpus, the labels or a count of anything, so it gets a table of its own and a
directory of its own (`instance/demo-scans/`), and the file is deleted the
moment a worker has finished with it. What stays is the result, for the hour
the page needs to show it; `ScanStore.prune` removes the row after that. No
address is stored: the allowance per visitor is in memory, as it is for the
generate demo.

`public_id` is what the page holds. Row ids count upward and this route takes
no token, so an integer would let anyone read the next visitor's result.

worker_heartbeats says which workers are alive, one row each. The scan page
asks before offering an upload, so a server with no photo worker says "photos
are not available here" instead of accepting one and never answering.

Revision ID: 0038_demo_scans
Revises: 0037_photo_identifications
"""

import sqlalchemy as sa
from alembic import op

revision = "0038_demo_scans"
down_revision = "0037_photo_identifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()
    if "demo_scans" not in tables:
        op.create_table(
            "demo_scans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("public_id", sa.Text(), nullable=False, unique=True),
            # photo | audio | video
            sa.Column("kind", sa.Text(), nullable=False),
            # NULL once the worker has finished and the file is gone.
            sa.Column("storage_ref", sa.Text()),
            sa.Column("latitude", sa.Float()),
            sa.Column("longitude", sa.Float()),
            sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("claimed_at", sa.Text()),
            sa.Column("finished_at", sa.Text()),
            sa.Column("error", sa.Text()),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("result", sa.Text()),
        )
        op.create_index("ix_demo_scans_state", "demo_scans", ["state", "kind"])
    if "worker_heartbeats" not in tables:
        op.create_table(
            "worker_heartbeats",
            sa.Column("name", sa.Text(), primary_key=True),
            sa.Column("seen_at", sa.Text(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
    op.drop_table("demo_scans")
