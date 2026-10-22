"""which bird called, by the role the recordist can actually see

0019 added a roster of named individuals. This is the field that will carry
nearly all the answers, because naming an individual crow needs bands and there
are none — what the recordist can read off behaviour is the bird's *standing* in
the family, and that is also the variable the 2026 León paper found its only
social-category-specific calls in (breeder versus helper).

The Poe family is exactly that shape: two parents, a yearling brood guard
(Edgar, about one year old), and two fledglings (about three months). Ages are
recorded here rather than in the app because they are facts about the family
this season, not about the vocabulary — a fledgling is a fledgling whatever
month it is.

`adult_unsure` is not padding. Telling a yearling helper from a breeding parent
at twenty metres is genuinely hard, and without a value for "an adult, I could
not tell which" the picker forces a guess — which is the failure experiment 0017
exists to prevent, arriving through the UI instead of through memory. Unknown
stays absent rather than being a value: a label with no caller_role means nobody
looked, and that must not become a claim.

Two fields, deliberately, and they answer different questions. `caller_role`
says what kind of bird called and will be set often. `crow_id` (0019) says which
individual, is nullable, and will be set rarely — Edgar is nameable, the two
parents are not, and pretending otherwise would put a fiction in the one table
that has to be ground truth.

Revision ID: 0020_caller_roles
Revises: 0019_crows
"""

from alembic import op
import sqlalchemy as sa

revision = '0020_caller_roles'
down_revision = '0019_crows'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'caller_roles',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key', sa.Text(), nullable=False, unique=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('active', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('version_introduced', sa.Integer(), nullable=False,
                  server_default='1'),
    )
    with op.batch_alter_table(
        'labels', table_kwargs={'sqlite_autoincrement': True}) as batch:
        batch.add_column(sa.Column('caller_role', sa.Text(), nullable=True))


def downgrade() -> None:
    raise NotImplementedError("not reversible")
