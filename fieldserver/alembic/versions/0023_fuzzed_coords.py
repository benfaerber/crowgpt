"""location precision gains a middle setting: coordinates within N miles

`fuzzed` snaps coordinates to an N-mile grid on the phone before they are
sent — territory-level truth with no street in it. Two columns carry it:

`contributors.fuzz_miles` is the grid size that contributor chose, which the
ingest backstop uses to re-snap coordinates from a client that got the rule
wrong. Nullable: everyone on exact or region has no radius, and a fuzzed
contributor whose radius has not arrived yet falls back to the default.

`captures.coord_fuzz_miles` is how coarse *this row's* coordinates are, stamped
per capture rather than read from the contributor — the setting can change
after the row lands, and a snapped fix with no mark would read as an exact one
forever. Null means the coordinates are as recorded.

No backfill: every existing row was sent exact or not at all.

Revision ID: 0023_fuzzed_coords
Revises: 0022_dictations
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_fuzzed_coords"
down_revision = "0022_dictations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contributors",
                  sa.Column("fuzz_miles", sa.Float(), nullable=True))
    op.add_column("captures",
                  sa.Column("coord_fuzz_miles", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("captures") as batch:
        batch.drop_column("coord_fuzz_miles")
    with op.batch_alter_table("contributors") as batch:
        batch.drop_column("fuzz_miles")
