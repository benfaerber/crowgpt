"""listening doses: a pool of trials served ten at a time

A crowgpt listening sitting has always been one self-contained HTML page, graded
in a single sitting of 50-60 trials, with the answers downloaded as JSON by hand.
Ben, 2026-08-05: *"It is hard to grade because most are so close it is hard to
pick."* He grades better in small doses and wants one page he returns to.

Three tables, and the shape of them is what protects the measurement.

`listening_pools` owns the pre-commitment. `question` is the criterion, written
down before the first clip, which every sitting in this project has done in the
page body. `reveal_at` is the new part: the trial count at which results may be
read. A page you return to invites checking the running total and stopping when
it looks resolved, and that is optional stopping — a nominal 5% test checked
repeatedly runs at 20-30%. The API refuses aggregates until `reveal_at` is met,
so the guard lives in the schema rather than in a listener's self-discipline.

`listening_trials` is fixed at build time and never reordered. `ordinal` is the
consumption order and `block` is the dose-sized group it belongs to. Blocks are
what make a multi-session design legitimate at all: 0038 measured 8.3 points of
listener drift between evening and morning on identical weights, so a dose is a
session and twenty doses are twenty sessions. If a dose carried one arm, drift
would become the dominant variable and the whole design would be worse than one
sitting. Every block therefore holds every arm in equal proportion, and every
trial holds both arms inside it, so drift cancels within a block and pooling
across blocks is sound.

`first_arm`/`second_arm` are the randomised presentation order, recorded because
the analysis has to undo it. They are also the reason the response can stop being
spatial: pooled over 317 non-catch pairwise trials, P(chose left) = 0.628, CI
[0.575, 0.681], resolved, while P(chose first-heard) = 0.495 — position, not
primacy. The graded response in `listening_answers` is a five-point scale, not a
side, so there is no left button to fall back on.

`listening_answers.grade` is -2..+2 relative to the FIRST clip: +2 is "the first
clip is much closer to the reference", 0 is "the same". Signed and graded on
purpose. A binary forced choice records one bit and throws away the confidence
Ben demonstrably has — he knows the arms are close — and 0 being a first-class
answer is what removes the pressure that feeds the button bias. `defects` carries
an optional taxonomy tag per clip, because his descriptions have located more
defects than his rankings have: "xylophone" found the dead codebooks, "crow +
modem" produced the churn measure, "too short clips instantly loose" exposed a
one-sided filter bias that had corrupted six experiments.

One answer per trial, enforced by a unique index and written as an upsert, so
changing your mind mid-dose is allowed and double-counting is not.

Audio is NOT stored here. `clip_dir` points at the pool's wav directory as built
by `crowgpt pool`, served read-only. The corpus is gitignored and derived units
from CC BY-NC-ND recordings are not redistributable; the answers are the durable
part, exactly as the experiments treat their numbers.

Revision ID: 0024_listening_doses
Revises: 0023_fuzzed_coords
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_listening_doses"
down_revision = "0023_fuzzed_coords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = sa.inspect(op.get_bind()).get_table_names()

    if "listening_pools" not in tables:
        op.create_table(
            "listening_pools",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("question", sa.Text(), nullable=False),
            sa.Column("clip_dir", sa.Text(), nullable=False),
            sa.Column("dose_size", sa.Integer(), nullable=False),
            sa.Column("reveal_at", sa.Integer(), nullable=False),
            sa.Column("spec", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("closed_at", sa.Text(), nullable=True),
            sa.UniqueConstraint("name", name="uq_listening_pools_name"),
        )

    if "listening_trials" not in tables:
        op.create_table(
            "listening_trials",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("pool_id", sa.Integer(),
                      sa.ForeignKey("listening_pools.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("ordinal", sa.Integer(), nullable=False),
            sa.Column("block", sa.Integer(), nullable=False),
            sa.Column("kind", sa.Text(), nullable=False),
            sa.Column("anchor_clip", sa.Text(), nullable=True),
            sa.Column("first_clip", sa.Text(), nullable=False),
            sa.Column("second_clip", sa.Text(), nullable=False),
            sa.Column("first_arm", sa.Text(), nullable=False),
            sa.Column("second_arm", sa.Text(), nullable=False),
            sa.Column("facts", sa.Text(), nullable=True),
            sa.UniqueConstraint("pool_id", "ordinal",
                                name="uq_listening_trials_pool_ordinal"),
        )
        op.create_index("ix_listening_trials_pool", "listening_trials",
                        ["pool_id", "ordinal"])

    if "listening_answers" not in tables:
        op.create_table(
            "listening_answers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("trial_id", sa.Integer(),
                      sa.ForeignKey("listening_trials.id", ondelete="CASCADE"),
                      nullable=False),
            sa.Column("grade", sa.Integer(), nullable=False),
            sa.Column("defects", sa.Text(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("decision_ms", sa.Integer(), nullable=True),
            sa.Column("plays_anchor", sa.Integer(), nullable=True),
            sa.Column("plays_first", sa.Integer(), nullable=True),
            sa.Column("plays_second", sa.Integer(), nullable=True),
            sa.Column("answered_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("trial_id", name="uq_listening_answers_trial"),
        )


def downgrade() -> None:
    raise NotImplementedError("not reversible")
