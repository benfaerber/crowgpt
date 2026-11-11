"""contributors record which upload policy they accepted, and what they allowed

Consent is per account (Ben, 2026-11-10): a recordist answers once, during
onboarding, and every capture they send is used under those answers. Captures
copy the generator answer into captures.generator_excluded at upload, so a
later change of mind does not rewrite what earlier recordings were sent under.

  policy_version       which version of the upload policy they accepted.
                       NULL means they never saw one, true of every account
                       made before onboarding existed.
  policy_accepted_at   when.
  allow_generator      1/0 for the generator use. NULL means never asked,
                       treated as allowed because nothing before this asked.
  allow_publish        1 only if they opted in to a future public dataset.
                       Opt-in: NULL and 0 both mean no.

Revision ID: 0036_contributor_consent
Revises: 0035_capture_provenance
"""

import sqlalchemy as sa
from alembic import op

revision = "0036_contributor_consent"
down_revision = "0035_capture_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("contributors") as batch:
        batch.add_column(sa.Column("policy_version", sa.Integer()))
        batch.add_column(sa.Column("policy_accepted_at", sa.Text()))
        batch.add_column(sa.Column("allow_generator", sa.Integer()))
        batch.add_column(sa.Column("allow_publish", sa.Integer()))


def downgrade() -> None:
    with op.batch_alter_table("contributors") as batch:
        for column in ("allow_publish", "allow_generator", "policy_accepted_at",
                       "policy_version"):
            batch.drop_column(column)
