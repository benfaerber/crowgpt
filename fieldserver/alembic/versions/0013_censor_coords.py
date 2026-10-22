"""split location precision into what is recorded and what is shown

One three-way setting — exact / exact_private / region — was carrying two
independent questions. Whether coordinates exist is about *recording*; whether
they are displayed is about *showing*. `exact_private` was the pair collapsed
into a middle option, which is why it needed a sentence to explain itself.

Now: `location_precision` answers the first (exact or region) and
`censor_coords` answers the second. The pair reproduces all three old states and
makes the fourth — region-only and censored — harmlessly redundant rather than
impossible.

The backfill is the dangerous part and the reason this is a revision rather than
a default. Somebody on `exact_private` chose "record them, never show them", so
they must land on exact + censor ON. Landing them on plain exact would put a
home address on a screen that had been deliberately hiding it, which is the one
failure this whole setting exists to prevent. Nobody is moved the other way:
`censor_coords` defaults to 0 only for rows that were never private.

Revision ID: 0013_censor_coords
Revises: 0012_capture_merges
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_censor_coords"
down_revision = "0012_capture_merges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contributors",
                  sa.Column("censor_coords", sa.Integer(), nullable=False,
                            server_default="0"))
    # Order matters: read the old value before overwriting it.
    op.execute("UPDATE contributors SET censor_coords = 1 "
               "WHERE location_precision = 'exact_private'")
    op.execute("UPDATE contributors SET location_precision = 'exact' "
               "WHERE location_precision = 'exact_private'")


def downgrade() -> None:
    op.execute("UPDATE contributors SET location_precision = 'exact_private' "
               "WHERE location_precision = 'exact' AND censor_coords = 1")
    with op.batch_alter_table("contributors") as batch:
        batch.drop_column("censor_coords")
