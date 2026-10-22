"""carry the call types a head also heard, not just the top one

A detected call has always stored one call type and one confidence, because
`SpeciesHead.predict` took argmax over the head's probabilities and dropped the
rest. That is lossy in a way the field noticed before the schema did: capture
104 holds an 18-second "begging" region with an adult cawing over the fledgling
at 12s and 27s, and neither caw appears anywhere in the database.

The runner-up was already being computed. This is where it lands.

`alternates` is JSON — a list of {call_type, confidence} above 0.3 — rather than
a table, because it is never queried across rows. It is read exactly once, with
the call it belongs to, to show "begging, and it also heard a call". A join
table would be the right shape for something aggregated; this is a detail of one
row and it travels with it.

`multi_label` records what kind of head produced them, and it is not decoration.
A one-vs-rest head's probabilities are independent, so a second high class means
it genuinely heard two things. A softmax's compete, so the same number means it
was torn between two readings of one thing. Storing the alternates without
storing which of those you are looking at would make the column unreadable a
month later — and both kinds exist right now, since only the American Crow head
has been retrained.

Existing rows get NULL and 0, which is honest: they were produced by a head that
could not answer this, not by one that answered "nothing else".

Revision ID: 0018_call_type_alternates
Revises: 0017_job_attempts
"""

from alembic import op
import sqlalchemy as sa

revision = '0018_call_type_alternates'
down_revision = '0017_job_attempts'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('detected_calls', sa.Column('alternates', sa.Text(), nullable=True))
    op.add_column('detected_calls',
                  sa.Column('multi_label', sa.Integer(), nullable=False,
                            server_default='0'))


def downgrade() -> None:
    raise NotImplementedError("not reversible")
