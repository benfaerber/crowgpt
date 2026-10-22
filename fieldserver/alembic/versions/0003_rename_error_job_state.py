"""rename the analysis job state 'error' to 'failed'

A data migration, not a schema one, which is why it spent its life inside a
store constructor: `AnalysisStore._init_schema` ran this UPDATE on every open,
forever, for the sake of rows written before the state was renamed.

That is what a migration is. Here it runs once and is recorded, and the store
constructor goes back to being a constructor.

Revision ID: 0003_rename_error_job_state
Revises: 0002_retire_pre_contributor
"""

from alembic import op

revision = "0003_rename_error_job_state"
down_revision = "0002_retire_pre_contributor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE analysis_jobs SET state = 'failed' WHERE state = 'error'")


def downgrade() -> None:
    # 'failed' is now also written by ordinary failures, so the two are no
    # longer distinguishable — reversing this would relabel rows that were
    # never called 'error'.
    raise NotImplementedError("'error' and 'failed' are no longer separable")
