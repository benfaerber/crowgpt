"""captures gain trigger for auto-recorded idle-mode captures

The phone's idle mode starts recordings with nobody present: a level gate
in the crow band trips, the pre-roll ring becomes the head of a file, and a
capture arrives here that no person witnessed. "auto" in this column is what
keeps those rows from masquerading as deliberate field recordings — their
observer role and distance are blank on purpose, and the thing that pressed
the button can be fooled by a siren.

Nullable, and null on every existing row, honestly: everything recorded
before this column existed was a person pressing a button, and null-means-
nobody-said stays the convention — no backfilled "manual" pretending the
question was asked. Wire version 23 is the client contract that sends it.

Revision ID: 0030_capture_trigger
Revises: 0029_generation_model
"""

from alembic import op
import sqlalchemy as sa


revision = "0030_capture_trigger"
down_revision = "0029_generation_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("trigger", sa.Text(), nullable=True))


def downgrade() -> None:
    raise NotImplementedError("not reversible")
