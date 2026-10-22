"""the field guide, served rather than shipped

Everything a recordist needs to know that is not obvious from the buttons: what
is worth recording, how to tell a fledgling from an adult, why silence counts.

Served from here rather than written into the app for the same reason the label
vocabulary is. What counts as a good recording is still being worked out — the
answer to "should I record this?" has already changed twice — and a phone that
has to be reinstalled to learn a better answer will keep giving the old one for
as long as it takes somebody to notice. Contributors are volunteers with their
own phones; there is no fleet update to schedule.

Structure mirrors `instructions`, which was one line each and is right for a
reminder beside a button. A guide needs a heading and a paragraph, so the text
lives in two translation namespaces keyed the same way — reusing the machinery
that already handles locales and config versions rather than adding a second.

Revision ID: 0011_guide_sections
Revises: 0010_label_vocabulary_version
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_guide_sections"
down_revision = "0010_label_vocabulary_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guide_sections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.Text(), nullable=False, unique=True),
        # Which part of the guide it belongs to: using the app, or reading the
        # birds. They are different kinds of knowledge and want separating.
        sa.Column("part", sa.Text(), nullable=False, server_default="using"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version_introduced", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("version_retired", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("guide_sections")
