"""keep the answer a label used to hold, instead of overwriting it

A label is a human judgement, and until now a second push with the same
`client_uuid` did `UPDATE labels SET call_type = ?` over the first one. That was
written for a real case — a labeller fixing a mistake before the push lands,
where storing both answers would put both into the training manifest — and it
quietly doubles as the only path for a *refinement*, which is a different thing
entirely. "I mistapped" and "I listened again three weeks later and that alarm
was a mob" arrive as the same request and the first answer is gone either way.

That distinction is about to start mattering. Splitting alarm into mobbing and
alerting means existing `alarm call` labels get re-heard and re-answered, and the
one measurement nobody can make afterwards is whether the finer vocabulary
actually changed anybody's mind — which needs both answers and the versions they
were chosen from.

WHY THE PREVIOUS VALUES MOVE, RATHER THAN THE ROW BEING SUPERSEDED BY A NEW ONE.
The obvious shape is `labels.superseded_by` pointing at a replacement row, and it
breaks two things. `context_events.label_id` references `labels(id)` — the
witnessed context of a call hangs off the label — so a refinement that mints a new
id leaves the dog that was barking attached to the answer nobody stands behind
any more. And `labels` is read in twelve places that all assume one row per
judgement, eight of them counts on the dashboard; every one would have to learn a
`WHERE superseded_by IS NULL` it currently doesn't need, and the one that forgot
would double-count silently.

So the id is stable, `labels` keeps meaning "what is believed now", and this
table holds what was believed before. Nothing that reads labels changes.

Revision ID: 0014_label_revisions
Revises: 0013_censor_coords
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_label_revisions"
down_revision = "0013_censor_coords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "label_revisions" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "label_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        # CASCADE because a retracted label's history is about nothing. Retracting
        # is already the deliberate act — "ground truth that cannot be taken back
        # is worse than none" — and keeping the drafts of a judgement that was
        # withdrawn would leave the corpus holding opinions with no owner.
        sa.Column("label_id", sa.Integer(),
                  sa.ForeignKey("labels.id", ondelete="CASCADE"), nullable=False),
        # The values as they stood *before* the change that created this row.
        sa.Column("call_type", sa.Text(), nullable=False),
        sa.Column("species", sa.Text(), nullable=False),
        # Nullable for the same reason labels.config_version is: a label made
        # before the column existed cannot say which vocabulary it was chosen
        # from, and inventing one would write a guess in as a fact.
        sa.Column("config_version", sa.Integer(), nullable=True),
        sa.Column("superseded_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_label_revisions_label", "label_revisions", ["label_id"])


def downgrade() -> None:
    raise NotImplementedError(
        "dropping this discards the only copy of what a labeller used to think"
    )
