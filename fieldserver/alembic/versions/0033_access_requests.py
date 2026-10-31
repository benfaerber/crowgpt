"""access_requests — who asked to try the app, and what Ben said

The field server is hosted and the app is a download, so the question "may I
have it?" needs a place to land that is not Ben's inbox. One row per request:
an email, a status, and once approved an invite token that unlocks the page
handing over the APK and the enrollment token. Nothing here is an account —
enrollment still happens from the phone, with the same shared secret as
before. This table only decides who gets told it.

Revision ID: 0033_access_requests
Revises: 218977d5773a
"""

import sqlalchemy as sa
from alembic import op

revision = "0033_access_requests"
down_revision = "218977d5773a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "access_requests" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "access_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("note", sa.Text()),
        # Where the form was posted from, for telling one person asking twice
        # from twenty asking once.
        sa.Column("requester_ip", sa.Text()),
        sa.Column("requested_at", sa.Text(), nullable=False),
        # pending | approved | declined
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("decided_at", sa.Text()),
        # The secret in the invite link. Plaintext on purpose: the link has to
        # be copyable from the dashboard after the fact, and what it unlocks
        # is the shared enrollment token, which already lives in the
        # environment of this same process.
        sa.Column("invite_token", sa.Text(), unique=True),
        sa.Column("emailed_at", sa.Text()),
        sa.Column("email_error", sa.Text()),
        sa.Column("downloads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_download_at", sa.Text()),
    )
    op.create_index("ix_access_requests_status", "access_requests", ["status"])
    op.create_index("ix_access_requests_email", "access_requests", ["email"])


def downgrade() -> None:
    op.drop_table("access_requests")
