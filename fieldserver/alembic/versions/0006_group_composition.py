"""how many birds were present, and how many were juveniles

Not recoverable from audio. A fledgling begging among five birds and one adult
calling alone are different recordings, and nothing in a WAV says which.

Three counters rather than two, which the existing descriptions decided. Of four
kept captures, only one splits by age ("2 fledglings 1 adult"); the rest say "3
crows on 1 branch" or "a single crow" with no age at all. A schema of adults and
juveniles could not hold those without inventing an age, so unaged is its own
bucket and the total is whatever the three add up to.

All nullable: not counting is the normal case and must stay distinguishable from
counting zero. Zero adults is a real observation about a group of fledglings.

Age is only judgeable close up — blue-grey eyes and a pink gape are invisible at
thirty metres — so distance_band is what says whether an age split is credible.

Revision ID: 0006_group_composition
Revises: 0005_distance_band
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_group_composition"
down_revision = "0005_distance_band"
branch_labels = None
depends_on = None

COLUMNS = ("adult_count", "juvenile_count", "unaged_count")


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("captures", sa.Column(column, sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("captures") as batch:
        for column in COLUMNS:
            batch.drop_column(column)
