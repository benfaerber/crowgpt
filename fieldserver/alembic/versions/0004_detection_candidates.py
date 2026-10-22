"""mark detections the model was unsure about as candidates

The analyzer used to discard anything under CROW_MIN_CONF = 0.25, which closed a
loop: it proposes, the recordist confirms, confirmations become training data —
so the corpus could only ever hold calls the model already scored well. A real
alarm call in capture 88 scored 0.183 and vanished silently; a begging fledgling
scored 0.06.

Rows in the 0.10–0.25 band are now kept and flagged. They are offered for
labelling and counted as nothing until a human rules on them: excluded from the
training export and from the calls x context matrix, exactly like a guess.

Existing rows are all confirmed — everything below the gate was thrown away
before it reached the database, so there is nothing to backfill.

Revision ID: 0004_detection_candidates
Revises: 0003_rename_error_job_state
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_detection_candidates"
down_revision = "0003_rename_error_job_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("detected_calls",
                  sa.Column("candidate", sa.Integer(), nullable=False,
                            server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("detected_calls") as batch:
        batch.drop_column("candidate")
