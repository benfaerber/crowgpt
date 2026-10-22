"""which captures were folded into which, and where each one landed

A stop-start field session produces one event as several captures: record,
stop, the crow caws again, record, stop. Captures 94-97 are ninety seconds of
one scene held as four rows, so anything counting events counts four and the
context and counts have to be entered four times.

Merging happens on the phone, which uploads the joined audio as an ordinary
capture — the server is handed one WAV and needs no idea it was assembled. What
it does need is a record of *which* captures that replaced, because otherwise
the parts and the whole sit side by side in the corpus with nothing saying they
are the same birds twice.

The parts are kept, rows and audio both. Deleting them would make the merge
irreversible, and the ★ Keep flag is the only thing telling real field audio
from seeded clips — a merge that dropped a kept capture would destroy the
scarcest thing here. So this table is the record that makes recovery possible,
and `offset_ms` is the part nobody could reconstruct later: it is what moves a
label back off the merged timeline and onto the part it was made against.

Deliberately not a `merged_into` column on captures. The offsets have to live
somewhere, and one table that holds the whole relationship cannot disagree with
itself the way a column plus a side table would.

Revision ID: 0012_capture_merges
Revises: 0011_guide_sections
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_capture_merges"
down_revision = "0011_guide_sections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capture_merges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # The capture that now holds the joined audio.
        sa.Column("merged_capture_id", sa.Integer(),
                  sa.ForeignKey("captures.id", ondelete="CASCADE"), nullable=False),
        # One of the captures it replaced. Kept, not deleted.
        sa.Column("part_capture_id", sa.Integer(),
                  sa.ForeignKey("captures.id", ondelete="CASCADE"), nullable=False),
        # Order within the merge, by recorded_at — 0 is the part whose metadata
        # the merged capture inherited.
        sa.Column("position", sa.Integer(), nullable=False),
        # Where this part begins on the merged timeline, including the silence
        # inserted before it. The one number that cannot be recomputed: it
        # depends on the gap the client used, which is free to change.
        sa.Column("offset_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("contributor_id", sa.Integer(),
                  sa.ForeignKey("contributors.id"), nullable=True),
        # A capture can only have been folded into one merge. Re-sending the
        # same merge is then an idempotent no-op rather than a second copy —
        # sync retries, and a retry must not double the record.
        sa.UniqueConstraint("part_capture_id", name="capture_merges_part_once"),
    )
    op.create_index("idx_capture_merges_merged", "capture_merges", ["merged_capture_id"])


def downgrade() -> None:
    op.drop_index("idx_capture_merges_merged", table_name="capture_merges")
    op.drop_table("capture_merges")
