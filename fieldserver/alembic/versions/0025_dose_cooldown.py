"""listening pools get a cooldown between doses

Ben, after grading the first dose of `churn-spread-0053`: *"can you also add a
timeout to enforce it. Only let me do 10 every [30] minutes."*

The dose design already assumed he would come back later; nothing made him. Asked
for as enforcement rather than as a suggestion, which is the right instinct — the
whole reason the pool is split into tens is that grading quality falls off, and a
rule you can talk yourself out of is not a rule. This is the same shape as
`reveal_at`: a guard in the schema rather than in a listener's self-discipline.

`cooldown_minutes` is per pool and nullable. Null means no cooldown, which is what
every pool registered before this revision gets — they were built without the
promise and silently locking one is worse than leaving it open.

MEASURED FROM THE LAST ANSWER, not from when a dose was handed out. Handing out is
a GET and Ben can reload the page, close the tab, or open it on the phone; if the
clock started there, a reload would cost him half an hour. The last `answered_at`
in the pool is a fact about work actually done.

WHY THE SERVER AND NOT A TIMER IN THE PAGE. A countdown in JavaScript is a
suggestion: it survives neither a reload nor a second browser, and the phone and
the laptop share this pool. The page still shows the countdown, but the dose
endpoint is what refuses.

The first dose's decision times say why this is worth enforcing at all: a median
of 121 s per trial against the old rig's 3,971 ms. He is listening properly now,
and that is exactly the thing that erodes when a sitting runs long.

Revision ID: 0025_dose_cooldown
Revises: 0024_listening_doses
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_dose_cooldown"
down_revision = "0024_listening_doses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {c["name"] for c in
               sa.inspect(op.get_bind()).get_columns("listening_pools")}
    if "cooldown_minutes" not in columns:
        op.add_column("listening_pools",
                      sa.Column("cooldown_minutes", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("listening_pools") as batch:
        batch.drop_column("cooldown_minutes")
