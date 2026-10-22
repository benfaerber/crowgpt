"""how far away the bird was, coarsely

The one variable that confounds every comparison between recordists and between
sites. A hooded crow in Berlin that tolerates a two-metre approach and an
American Crow thirty metres up a rooftop produce audio that differs in signal-to-
noise, in spectral tilt, and in how much of the call clears the street — before
either bird has said anything different.

Experiment 0003 already hit this: the spectral gap between two call types
survived an SNR control, but had to be reported as distance-contaminated, with
duration and rhythm as the only trustworthy measures. Across two continents that
stops being a caveat and becomes the result.

Nothing in a WAV says how far away the bird was, and no analysis recovers it. So
it is recorded at capture time or it is lost — the same reasoning as the
microphone provenance, and the same one-tap cost.

Coarse on purpose. "About twenty metres" is a real answer from a person looking
at a bird; metres to a decimal place would be invented precision.

Revision ID: 0005_distance_band
Revises: 0004_detection_candidates
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_distance_band"
down_revision = "0004_detection_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("captures", sa.Column("distance_band", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("captures") as batch:
        batch.drop_column("distance_band")
