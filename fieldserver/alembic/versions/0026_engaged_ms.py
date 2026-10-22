"""listening answers get an engaged time that is not tab-open time

`decision_ms` has been measured the same way by every listening page in this
project — wall-clock from the trial rendering to the answer being submitted — and
it is not a decision time. It counts the tab sitting open.

This was found the expensive way. The first dose of `churn-spread-0053` reported a
median of 121 s per trial against the old rig's 3,971 ms, and that was read as
evidence the new graded response was making Ben listen harder. Ben: *"yeah i musta
just forgot. Its not real. I prolly spent like 5-10 per."* Two conclusions had
been drawn from it inside one session — that the new response helped, and that
dose 2's fall from 113 s to 64 s was a fatigue signal — and both were idle time.

The field is not dropped, because difficulty is the thing this pool is actually
about: Ben's summary of the old rig was *"most are so close it is hard to pick"*,
so time per trial is worth having. It is replaced by one that can survive contact
with a real listener:

`engaged_ms` starts at the FIRST PLAY, not at render. A trial that renders while
he is reading something else costs nothing until he presses play, which is the
first moment he is doing the task.

It also PAUSES WHILE THE TAB IS HIDDEN, via the Page Visibility API. Switching to
another window mid-trial is the specific thing that produced 121 s, and a timer
that cannot see it will keep producing numbers like that.

`decision_ms` is kept rather than removed. It is honest wall-clock and it is what
every earlier session recorded, so deleting it would silently change what the
older saved sittings mean. Its docstring now says what it is. The 20 trials graded
before this revision have `engaged_ms` NULL, which is correct — nobody measured
it — and their `decision_ms` should be treated as unusable rather than as a
baseline.

Revision ID: 0026_engaged_ms
Revises: 0025_dose_cooldown
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_engaged_ms"
down_revision = "0025_dose_cooldown"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in
               sa.inspect(op.get_bind()).get_columns("listening_answers")}
    if "engaged_ms" not in columns:
        op.add_column("listening_answers",
                      sa.Column("engaged_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("listening_answers") as batch:
        batch.drop_column("engaged_ms")
