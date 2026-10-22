"""how many times a job has been handed to a worker

A claimed job had no way back. `claim_next` sets state='running' and nothing
ever un-sets it, so a worker that is killed mid-analysis — OOM, a crashed
laptop, Ctrl-C at the wrong second — leaves the job running forever and its
capture stuck in 'analyzing', which is non-terminal and therefore counted by
nothing. The capture disappears from every needs-work number on the dashboard
and the only way to notice is to open the database.

Requeuing on worker startup fixes that, and introduces the failure it has to be
guarded against: a job that kills the worker gets requeued by the restart,
kills it again, and the pair of them loop for as long as anyone lets them. So
the count, and a ceiling on it — after which the job is failed like any other
and its capture handed back, which is a state somebody can actually see.

Existing rows start at 0. Every one of them is terminal today, so the number is
only ever read for jobs claimed after this lands.

Revision ID: 0017_job_attempts
Revises: 0016_ai_descriptions
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_job_attempts"
down_revision = "0016_ai_descriptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_jobs", sa.Column(
        "attempts", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("analysis_jobs") as batch:
        batch.drop_column("attempts")
