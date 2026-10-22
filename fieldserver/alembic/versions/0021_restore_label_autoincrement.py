"""put AUTOINCREMENT back on labels.id

0019 added a foreign key to `labels`, which forces alembic's batch mode to
rebuild the table — and a rebuild that does not pass `sqlite_autoincrement`
drops AUTOINCREMENT from the primary key. 0019 and 0020 have since been fixed,
so a fresh database never loses it; this is for the ones that already ran the
broken versions.

Why it is not cosmetic. Without AUTOINCREMENT, SQLite hands out the highest
rowid + 1 — which *falls* when the highest row is deleted, so a new label can be
given a retracted label's id. Three tables key on `label_id`: `ai_descriptions`,
`context_events` and `label_revisions`. A recycled id silently attaches a
retracted label's witnessed context, and a machine-written description of the
call it used to be, to whatever label takes its number next. Both would read as
ordinary data; nothing anywhere would flag it.

`ai_descriptions` exists precisely because a description must outlive the label
it was written for, keyed on the span rather than the answer. Recycling ids
turns that survival into a hazard.

Caught by tests/test_ai_descriptions.py::TestItOutlivesTheLabel, which asserts a
replacement label gets a different row id. It was already there and it worked.

Revision ID: 0021_restore_label_autoincrement
Revises: 0020_caller_roles
"""

from alembic import op

revision = '0021_restore_label_autoincrement'
down_revision = '0020_caller_roles'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # recreate='always' is the whole migration. Batch mode defaults to
    # recreate='auto', which rebuilds only when an operation needs it — and this
    # one has no operations, so 'auto' correctly decides to do nothing and the
    # AUTOINCREMENT never comes back. Forcing the rebuild is what applies the
    # table kwarg. On a database that already has it this copies the table to
    # the same shape and changes nothing.
    with op.batch_alter_table(
            'labels', recreate='always',
            table_kwargs={'sqlite_autoincrement': True}):
        pass


def downgrade() -> None:
    raise NotImplementedError("not reversible")
