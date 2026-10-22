"""individual crows, so a label can say which bird called

Experiment 0017 asked whether the audio identifies the caller and answered no:
five crows in one recording produce the cluster structure one crow produces, and
what structure exists tracks where the bird was standing rather than who it was.
So attribution cannot be recovered later, by us or by a model.

But the recordist can often name a bird *live*, watching it call. Capture 103's
observation already does it in prose — "4 fly, Edgar watches from top of apt" —
because there is nowhere structured to put it. This is that place.

`crows` hangs off a family rather than off a capture, which is the shape
`FamilyStore`'s docstring reserved. A caller has to be a bird already on the
roster, so one cannot be invented per capture and "Edgar" means the same bird in
July and in October. That is the whole value: an identity that survives across
recordings.

Three rules the schema enforces rather than documents:

  * `labels.crow_id` is NULLABLE and stays that way. Unknown is a real answer —
    most calls have no visible caller — and a default would turn "nobody looked"
    into "nobody was there", which is the failure the observer_role picker's
    "Not said" option exists to avoid.
  * ON DELETE SET NULL, not CASCADE. Removing a bird from the roster must not
    delete the labels attributed to it; the calls still happened.
  * `attributed_at` records WHEN the attribution was made, so a caller filled in
    from memory an hour later is distinguishable from one recorded while the
    bird was calling. 0017 is the reason: an attribution from memory is the
    fabrication this feature exists to avoid, and a column that cannot tell them
    apart would launder one into the other.

`role` is free text on purpose. Ben has no bands and reads role off behaviour —
parent, helper, fledgling — and the Poe family's structure (Edgar is a yearling
brood guard) is exactly the breeder-versus-helper variable the 2026 León paper
found its only social-category-specific calls in. A closed enum here would have
to be guessed now and migrated later.

Revision ID: 0019_crows
Revises: 0018_call_type_alternates
"""

from alembic import op
import sqlalchemy as sa

revision = '0019_crows'
down_revision = '0018_call_type_alternates'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'crows',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('family_id', sa.Integer(),
                  sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        # parent / helper / fledgling / whatever the recordist can actually see.
        sa.Column('role', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Text(), nullable=False),
        # Idempotent push, same as families and captures: the app creates these
        # offline and a retry after a lost response must not duplicate a bird.
        sa.Column('client_uuid', sa.Text(), nullable=True),
        sa.Column('contributor_id', sa.Integer(),
                  sa.ForeignKey('contributors.id'), nullable=True),
        sa.UniqueConstraint('family_id', 'name', name='uq_crows_family_name'),
    )
    op.create_index('ix_crows_family', 'crows', ['family_id'])

    # sqlite_autoincrement is NOT optional here. Adding a foreign key forces
    # batch mode to rebuild the table, and a rebuild that does not say this
    # silently drops AUTOINCREMENT from labels.id — after which SQLite recycles
    # the highest rowid on delete. `ai_descriptions`, `context_events` and
    # `label_revisions` all key on label_id, so a recycled id silently attaches
    # a retracted label's description and witnessed context to whatever label
    # takes its number next. Caught by
    # tests/test_ai_descriptions.py::TestItOutlivesTheLabel.
    with op.batch_alter_table(
        'labels', table_kwargs={'sqlite_autoincrement': True}) as batch:
        batch.add_column(sa.Column('crow_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('attributed_at', sa.Text(), nullable=True))
        batch.create_foreign_key('fk_labels_crow', 'crows', ['crow_id'], ['id'],
                                 ondelete='SET NULL')


def downgrade() -> None:
    raise NotImplementedError("not reversible")
