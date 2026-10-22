"""machine-written descriptions, keyed to a span of audio rather than to a label

The recordist's own words are scarce: half the kept captures carry no written
note at all, because typing in the field competes with the field. A model can
read the audio, the detections and the quality numbers and write the long version
afterwards. That is worth having, and it is worth being unable to mistake for
testimony.

SO IT IS NOT A COLUMN ON `captures`, AND NOT ONE ON `labels` EITHER.

Not on `captures`, because Ben wants the detail per call as well as per
recording, and a second column on a second table would need a second writer, a
second reader and a second set of rules about what it means.

Not on `labels`, because it would not survive. Re-answering a call type from the
phone is a delete-and-recreate — `AppServices.removeLabel` calls
`DELETE /api/labels/<id>`, the row goes, `context_events.label_id` cascades with
it, and the replacement is a new row with a new id. A description that cost a
model a minute of reading would vanish on a stray tap, silently, exactly the way
context chips already do. The skill warns human labellers about that trap; a
schema should not walk into it.

Keyed on the span instead: `(capture_id, start_sec, end_sec)`, with a NULL span
meaning the recording as a whole. Spans are immutable — no code path updates a
label's `start_sec`/`end_sec`, which is precisely what makes them a stable key —
so a description written today survives the label being re-answered, retracted,
re-created, or never created at all. That is the durability Ben asked for: if the
labelling flow changes, or `alarm call` splits into mob and alert the way
FUTURE.txt plans, the underlying detail is still attached to the audio it
describes and the new answer can be derived from it rather than re-listened for.

NULL SPANS NEED THEIR OWN INDEX. SQLite treats NULL as distinct from NULL in a
UNIQUE constraint, so `UNIQUE(capture_id, start_sec, end_sec)` would happily
store a hundred capture-level rows. Two partial indexes instead: one capture-level
row per capture, one row per distinct span.

`model` and `written_at` travel with the text, following `analysis_results`,
which keeps `model_version` and `created_at` beside its output for the same
reason: a guess whose author and date are unknown cannot be judged later, and a
description written before a crop or a re-analysis is stale in a way nothing else
would reveal.

This is a guess, and the rules that apply to guesses apply here. It must never
reach the training manifest — `behavior_guess` was kept out of the export on the
same grounds — and anything reading it to propose labels has to weigh it below
the recordist and no higher than a detection, or the model ends up marking its
own homework.

Revision ID: 0016_ai_descriptions
Revises: 0015_capture_quality
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_ai_descriptions"
down_revision = "0015_capture_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "ai_descriptions" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "ai_descriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("capture_id", sa.Integer(),
                  sa.ForeignKey("captures.id", ondelete="CASCADE"),
                  nullable=False),
        # NULL/NULL is the recording as a whole. A span is stored even when a
        # label covers the same seconds, and deliberately not joined to it: the
        # label is an answer and this is a description, and they have different
        # lifetimes.
        sa.Column("start_sec", sa.Float(), nullable=True),
        sa.Column("end_sec", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        # What wrote it. Free text like analysis_results.model_version, because
        # the useful string is whatever identifies the run, not an enum this
        # schema would have to keep up with.
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("written_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_ai_descriptions_capture", "ai_descriptions", ["capture_id"],
    )
    op.create_index(
        "ux_ai_descriptions_whole", "ai_descriptions", ["capture_id"],
        unique=True, sqlite_where=sa.text("start_sec IS NULL"),
    )
    op.create_index(
        "ux_ai_descriptions_span", "ai_descriptions",
        ["capture_id", "start_sec", "end_sec"],
        unique=True, sqlite_where=sa.text("start_sec IS NOT NULL"),
    )


def downgrade() -> None:
    # Dropping this loses model output rather than fieldwork: it can be written
    # again from the audio, which is the difference between it and `labels`.
    op.drop_table("ai_descriptions")
