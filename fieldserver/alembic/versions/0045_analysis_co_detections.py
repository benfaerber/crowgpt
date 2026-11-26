"""carry high-confidence co-detected raptors on analysis_results

BirdNET runs over the whole recording on every analysis job and previously threw
away every non-corvid detection. Keeping true taxonomic raptors above 0.70
(experiment 0121) costs nothing at inference, surfaces honest co-detections on
the dashboard ("BirdNET also heard: Cooper's Hawk (0.74)", never as context or
cause), and records when a vocal raptor was present on the audio.

Stored on `analysis_results` rather than `detected_calls` because a raptor can
call in a silent gap between two crow regions (or when no corvid cleared the
threshold at all). Existing rows keep NULL, which decodes to `[]` at read time.

Revision ID: 0045_analysis_co_detections
Revises: 0044_banned_addresses
"""

import sqlalchemy as sa
from alembic import op

revision = "0045_analysis_co_detections"
down_revision = "0044_banned_addresses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("analysis_results")}
    if "co_detections_json" in cols:
        return
    op.add_column("analysis_results", sa.Column("co_detections_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("analysis_results") as batch:
        batch.drop_column("co_detections_json")
