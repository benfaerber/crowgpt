"""scan desk — a visitor labels the scan they let the project keep

Revision 0039 kept a visitor's file and nothing ever read it: no page listed
`scan_contributions`, and the person who had just heard the recording made
was asked nothing about it. They are the only witness to what was happening,
and the page's hour was the whole of their time with the project.

Three things change that.

`scan_contributions.public_id` is the scan's own unguessable id, carried over
when the file is kept, so the visitor's link still means something after the
`demo_scans` row is pruned. It is the only credential the labelling desk
takes: whoever holds the link may label that one recording.

`scan_labels` and `scan_context` are what they say there, in the same shape
the phone pushes (a span and a call type; a context key attached to a label
by the label's own uuid, or to the whole recording when a visitor says it
holds no calls). Their own tables, for the reason 0039 gives: a contribution
is NOT A CAPTURE, and a stranger's answers are not `labels` until an
operator has listened and promoted the recording.

`promoted_capture_id` is that promotion: the capture the contribution became.
The contribution row stays, so the visitor's link keeps answering.

Revision ID: 0041_scan_desk
Revises: 0040_invite_enrollment
"""

import sqlalchemy as sa
from alembic import op

revision = "0041_scan_desk"
down_revision = "0040_invite_enrollment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("scan_contributions")}
    if "public_id" not in existing:
        op.add_column("scan_contributions", sa.Column("public_id", sa.Text()))
        op.create_index("ix_scan_contributions_public_id", "scan_contributions",
                        ["public_id"], unique=True)
    if "silent_confirmed_at" not in existing:
        op.add_column("scan_contributions", sa.Column("silent_confirmed_at", sa.Text()))
    if "promoted_capture_id" not in existing:
        op.add_column("scan_contributions", sa.Column("promoted_capture_id", sa.Integer()))
    tables = inspector.get_table_names()
    if "scan_labels" not in tables:
        op.create_table(
            "scan_labels",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("contribution_id", sa.Integer(),
                      sa.ForeignKey("scan_contributions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("client_uuid", sa.Text(), nullable=False),
            sa.Column("start_sec", sa.Float(), nullable=False),
            sa.Column("end_sec", sa.Float(), nullable=False),
            sa.Column("call_type", sa.Text(), nullable=False),
            sa.Column("caller_role", sa.Text()),
            sa.Column("from_detection", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("config_version", sa.Integer()),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("contribution_id", "client_uuid", name="uq_scan_labels_uuid"),
        )
    if "scan_context" not in tables:
        op.create_table(
            "scan_context",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("contribution_id", sa.Integer(),
                      sa.ForeignKey("scan_contributions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("client_uuid", sa.Text(), nullable=False),
            # The scan_labels.client_uuid this belongs to; NULL is "during the
            # whole recording", which only a silent one uses.
            sa.Column("label_uuid", sa.Text()),
            sa.Column("key", sa.Text(), nullable=False),
            sa.Column("start_sec", sa.Float()),
            sa.Column("end_sec", sa.Float()),
            sa.Column("config_version", sa.Integer()),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("contribution_id", "client_uuid", name="uq_scan_context_uuid"),
        )


def downgrade() -> None:
    op.drop_table("scan_context")
    op.drop_table("scan_labels")
    op.drop_index("ix_scan_contributions_public_id", table_name="scan_contributions")
    with op.batch_alter_table("scan_contributions") as batch:
        batch.drop_column("promoted_capture_id")
        batch.drop_column("silent_confirmed_at")
        batch.drop_column("public_id")
