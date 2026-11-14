"""an invite carries its own enrollment code, and a contributor remembers its invite

Until now an approved invite's page showed the fleet's one enrollment token,
the same string every phone has typed since the beginning. Ten people had
been shown it by the time this was written, and none of them could be turned
away again without changing it for everybody.

`access_requests.enroll_code` is the string an invite's page shows instead.
/api/devices/register takes it wherever it took the shared token, so the app
does not change. It works while the request is approved and has enrolled
fewer phones than `enrollments` is allowed to reach; declining the request
ends it for that person alone. Plaintext for the reason `invite_token` is:
the page has to be able to show it again.

`contributors.access_request_id` is the invite a contributor came in on, NULL
for everyone enrolled with the shared token (the operator's own phones). It
is what an upload quota is keyed on (core/quota.py) and what says whose
recordings an invite produced. No foreign key: SQLite would need the table
rebuilt for it, and a request row is never deleted.

Requests approved before this revision get a code here, so "approved" always
means "has one".

Revision ID: 0040_invite_enrollment
Revises: 0039_scan_contributions
"""

import secrets

import sqlalchemy as sa
from alembic import op

revision = "0040_invite_enrollment"
down_revision = "0039_scan_contributions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    requests = {column["name"] for column in inspector.get_columns("access_requests")}
    if "enroll_code" not in requests:
        op.add_column("access_requests", sa.Column("enroll_code", sa.Text()))
        op.create_index("ix_access_requests_enroll_code", "access_requests",
                        ["enroll_code"], unique=True)
    if "enrollments" not in requests:
        op.add_column("access_requests",
                      sa.Column("enrollments", sa.Integer(), nullable=False, server_default="0"))
    if "access_request_id" not in {c["name"] for c in inspector.get_columns("contributors")}:
        op.add_column("contributors", sa.Column("access_request_id", sa.Integer()))
    approved = bind.execute(sa.text(
        "SELECT id FROM access_requests WHERE status = 'approved' AND enroll_code IS NULL")).fetchall()
    for (request_id,) in approved:
        bind.execute(sa.text("UPDATE access_requests SET enroll_code = :code WHERE id = :id"),
                     {"code": secrets.token_urlsafe(12), "id": request_id})


def downgrade() -> None:
    with op.batch_alter_table("contributors") as batch:
        batch.drop_column("access_request_id")
    op.drop_index("ix_access_requests_enroll_code", table_name="access_requests")
    with op.batch_alter_table("access_requests") as batch:
        batch.drop_column("enrollments")
        batch.drop_column("enroll_code")
