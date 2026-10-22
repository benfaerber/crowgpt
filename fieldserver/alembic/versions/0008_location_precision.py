"""how precisely a contributor is willing to say where they were

A crow corpus is a map of where one person walks. Forty captures with fixes
describe a home, a commute and a routine — true of every contributor who joins,
not just the one who built it. Coordinates are also genuinely needed: BirdNET's
species filter takes lat/lon, and "does this call differ by territory" cannot be
asked without them. So it is a choice rather than a policy.

`region` is stored on the capture rather than derived from its coordinates on
demand. Two reasons, and the second is the point of the feature: a capture at
`region` precision has no coordinates to derive anything from, and one recorded
in another state should say so rather than inherit the contributor's home.

Format is "Utah, US" — region and country, nothing finer. A city is already too
small in a rural area, and the question the corpus asks of place is which
population was recorded.

Revision ID: 0008_location_precision
Revises: 0007_device_logs
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_location_precision"
down_revision = "0007_device_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("region", sa.Text(), nullable=True))
    # Defaulting to 'exact' rather than the safest option on purpose: every row
    # that exists was recorded under that understanding, and pretending
    # otherwise would relabel data rather than protect anyone. New contributors
    # are asked.
    op.add_column("contributors", sa.Column(
        "location_precision", sa.Text(), nullable=False, server_default="exact"))
    # Where they are, when a capture has no fix to say for itself.
    op.add_column("contributors", sa.Column("region", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("contributors") as batch:
        batch.drop_column("region")
        batch.drop_column("location_precision")
    with op.batch_alter_table("captures") as batch:
        batch.drop_column("region")
