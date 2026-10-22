"""generations — chat with CrowGPT: a request for a call, and the clip that answers

The dashboard gets a chat page: press "alarm call" and the request shows as a
message, the generated clip arrives as the reply. Each row here is one such
exchange — the request half is written at enqueue, the reply half when the
generation worker finishes.

ONE TABLE, NOT THE DICTATIONS PAIR. Dictations split artifact from job because
the artifact arrives first (an upload) and the job produces a second thing (a
transcript). Here the job's product IS the artifact, there is no upload half,
and a generation that loses its job row would be an unattributed wav on disk —
so the exchange and its lifecycle are one row, and "done with no clip" is
unrepresentable the same way dictations made it.

The wavs live in `instance/generated/`, never `instance/media/`, for the media
directory's standing invariant: everything in it is somebody's actual recording
of birds. A synthetic caw filed there would be one bad ORDER BY away from being
analysed as field audio — the exact confusion the ★ Keep flag exists to hold
back, manufactured in-house.

The seed is chosen at request time and stored, so a generation is reproducible
from its row alone, and the sampling settings are recorded by the worker that
actually used them rather than assumed from whatever the defaults were later.

Revision ID: 0028_generations
Revises: 0027_fold_contributor_backfill
"""

import sqlalchemy as sa
from alembic import op

revision = "0028_generations"
down_revision = "0027_fold_contributor_backfill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()

    if "generations" not in tables:
        op.create_table(
            "generations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("call_type", sa.Text(), nullable=False),
            # Fixed at enqueue so the clip is reproducible from the row.
            sa.Column("seed", sa.Integer(), nullable=False),
            sa.Column("requested_by", sa.Integer(), sa.ForeignKey("contributors.id")),
            sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("claimed_at", sa.Text()),
            sa.Column("finished_at", sa.Text()),
            sa.Column("error", sa.Text()),
            sa.Column("created_at", sa.Text(), nullable=False),
            # The reply half, written by the worker on completion.
            sa.Column("storage_ref", sa.Text()),
            sa.Column("duration_sec", sa.Float()),
            sa.Column("model", sa.Text()),
            sa.Column("temperature", sa.Float()),
            sa.Column("top_k", sa.Integer()),
        )
        op.create_index("ix_generations_state", "generations", ["state"])


def downgrade() -> None:
    """Drops the table; the wavs stay in `instance/generated/` unattributed.

    They are synthetic audio with no rights question attached, so the orphaning
    is untidy rather than harmful. A development action only.
    """
    op.drop_table("generations")
