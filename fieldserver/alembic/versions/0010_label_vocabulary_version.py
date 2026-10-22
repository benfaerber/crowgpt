"""which vocabulary a label was chosen from

A label records what somebody decided, and the meaning of that decision lives in
the vocabulary they were shown. Retire a tag, split a call type in two, and
every label made under the old version is ambiguous — with nothing to say which
ones those are.

The obvious substitute is arithmetic on `created_at` against
`config_versions.published_at`, and it does not work: the phone caches the
vocabulary and labels offline, so a capture labelled in a park on Tuesday used
whatever version that handset last fetched — possibly three behind what this
server considered current at that moment. Only the phone knows, so the phone
sends it.

`version_retired` is the other half. Definitions already recorded when they
arrived (`version_introduced`); retirement only flipped `active`, so the
vocabulary knew when a tag appeared but not when it left. A relabel queue needs
both ends: a label is worth revisiting when its definition was retired after it
was made, or reintroduced after it was made — the second being the genuinely
dangerous case, where a key comes back meaning something else.

All nullable. Every label that already exists predates the question, and
inventing a version for one made a month ago would write a guess into the
corpus as a fact.

Revision ID: 0010_label_vocabulary_version
Revises: 0009_pcm_sha256
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_label_vocabulary_version"
down_revision = "0009_pcm_sha256"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("labels", sa.Column("config_version", sa.Integer(), nullable=True))
    op.add_column("context_events", sa.Column("config_version", sa.Integer(), nullable=True))
    op.add_column("label_defs", sa.Column("version_retired", sa.Integer(), nullable=True))
    op.add_column("context_defs", sa.Column("version_retired", sa.Integer(), nullable=True))


def downgrade() -> None:
    for table, column in (
        ("context_defs", "version_retired"),
        ("label_defs", "version_retired"),
        ("context_events", "config_version"),
        ("labels", "config_version"),
    ):
        with op.batch_alter_table(table) as batch:
            batch.drop_column(column)
