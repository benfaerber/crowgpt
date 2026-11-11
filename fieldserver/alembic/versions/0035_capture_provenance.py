"""captures learn where they came from and what they may be used for

Until now every capture was recorded in the app by someone who enrolled, so
"what may this be used for" had one answer and needed no column. Recordings
shared from outside the app (the first: ten clips sent by a crow enthusiast,
2026-11-10) arrive with terms their recordist set by hand, and a promise kept
only in a notes field is a promise the next training script will not read.

  provenance          'app' for anything the field app recorded, 'shared' for
                      audio a recordist sent some other way. Only 'app'
                      captures are ever candidates for a public dataset; that
                      was the condition the first shared clips were sent on.
  generator_excluded  1 when the recordist said no to the generator. Any reader
                      that feeds generator training must filter on it. None
                      does today (crowgpt's corpus skips field audio entirely),
                      which is luck, not a guarantee.

Revision ID: 0035_capture_provenance
Revises: 0034_demo_generations
"""

import sqlalchemy as sa
from alembic import op

revision = "0035_capture_provenance"
down_revision = "0034_demo_generations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("captures") as batch:
        batch.add_column(sa.Column("provenance", sa.Text(), nullable=False,
                                   server_default="app"))
        batch.add_column(sa.Column("generator_excluded", sa.Integer(),
                                   nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("captures") as batch:
        batch.drop_column("generator_excluded")
        batch.drop_column("provenance")
