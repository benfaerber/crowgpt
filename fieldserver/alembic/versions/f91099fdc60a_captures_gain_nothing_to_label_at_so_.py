"""captures gain nothing_to_label_at, so the label queue can empty

Labelling is the only thing in this project that cannot be recovered later — a
missed sync is re-run tomorrow, a missed label lives in a memory that fades
within hours. The label queue exists to catch that, and a queue is only as good
as its ability to become empty: one that lists recordings nobody will ever label
is ignored within a week, and then it is worse than no queue at all.

This is the column that lets a recording leave the queue without being labelled.

DELIBERATELY NOT silent_confirmed_at, which already exists and is the obvious
place to put it. That one says a human listened to the whole recording and heard
no crow calls — an observation about crows, and the denominator every "how often
did they call at X" question needs. This one says the recording is not field
material: a test upload, a seeded archive clip, a walk that caught nothing but
traffic. Folding them together would quietly file every test upload as a
listened-to, genuinely quiet morning, which is the corpus contaminant the ★ Keep
flag was invented to keep out.

Revision ID: f91099fdc60a
Revises: 0021_restore_label_autoincrement
"""

from alembic import op
import sqlalchemy as sa


revision = 'f91099fdc60a'
down_revision = '0021_restore_label_autoincrement'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable, and NULL is the meaningful default: it says nobody has decided
    # either way, which is exactly what "waiting in the queue" means. A NOT NULL
    # column with a timestamp default would mark every capture ever recorded as
    # already dealt with.
    op.add_column(
        "captures",
        sa.Column("nothing_to_label_at", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    raise NotImplementedError("not reversible")
