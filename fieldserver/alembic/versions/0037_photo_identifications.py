"""photo_identifications — a photo an operator uploaded, and what the classifier called it

The dashboard gets a Photo ID page: upload a photo, the photo worker names the
corvid in it. Each row is one such exchange, built the way generations is: the
request half (the stored photo, optional coordinates) is written at upload,
the reply half (`result`, the ranked species as JSON) when the worker finishes.
One table, because a result with no photo and a photo with no job are both
states nobody wants to represent.

The photos live in `instance/photo-id/`, never `instance/media/`: that
directory means somebody's field recording, and these are test uploads for a
classifier. Nothing here is a capture or becomes one.

Coordinates are nullable. When they are NULL the worker reads the photo's own
GPS tags, and the coordinates it actually used are recorded in `result`.

Revision ID: 0037_photo_identifications
Revises: 0036_contributor_consent
"""

import sqlalchemy as sa
from alembic import op

revision = "0037_photo_identifications"
down_revision = "0036_contributor_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "photo_identifications" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "photo_identifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("storage_ref", sa.Text(), nullable=False),
        sa.Column("original_name", sa.Text()),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("contributors.id")),
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claimed_at", sa.Text()),
        sa.Column("finished_at", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.Text(), nullable=False),
        # The reply half: ranking, bird box, frame size, coordinates used.
        sa.Column("result", sa.Text()),
    )
    op.create_index("ix_photo_identifications_state", "photo_identifications", ["state"])


def downgrade() -> None:
    """Drops the table; the uploads stay in `instance/photo-id/` unattributed.
    A development action only."""
    op.drop_table("photo_identifications")
