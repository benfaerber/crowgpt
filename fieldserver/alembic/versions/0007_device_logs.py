"""what the phone was doing when something went wrong

A field app is debugged by whoever is holding it, and they are outdoors with
one hand full of phone and no cable. adb logcat is only true while the USB
cable is attached, and it is cleared by the reinstall that was supposed to fix
the thing being diagnosed — which is exactly how the prepareAsync crash on the
Pixel 10 was lost twice.

So the phone keeps its own log and pushes it up with everything else. These
rows are *disposable*, unlike every other table here: a capture is data, a log
line is a hint about the app. Anything that reads them should be prepared for
them to have been pruned.

Deliberately not `ON DELETE CASCADE` from devices in the sense that matters —
`at` is the phone's clock and `received_at` is ours, because a phone that has
been offline for a week uploads a week-old line and the difference between
those two timestamps is itself diagnostic.

UNIQUE(device_id, client_uuid) is what makes re-sending a batch free. The phone
marks lines sent only after the server confirms, so a dropped response means it
sends them again, and it must not double them.

Revision ID: 0007_device_logs
Revises: 0006_group_composition
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_device_logs"
down_revision = "0006_group_composition"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id"),
                  nullable=False),
        sa.Column("contributor_id", sa.Integer(), sa.ForeignKey("contributors.id"),
                  nullable=False),
        sa.Column("client_uuid", sa.Text(), nullable=False),
        # The phone's clock when the line was written.
        sa.Column("at", sa.Text(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        # Which part of the app spoke: recorder, sync, db, app.
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        # JSON, free-form. Stack traces, ids, sizes.
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("app_version", sa.Integer(), nullable=True),
        sa.Column("app_commit", sa.Text(), nullable=True),
        sa.Column("received_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("device_id", "client_uuid", name="device_logs_client_uuid"),
    )
    op.create_index("device_logs_at", "device_logs", ["at"])
    op.create_index("device_logs_level", "device_logs", ["level"])


def downgrade() -> None:
    op.drop_index("device_logs_level", table_name="device_logs")
    op.drop_index("device_logs_at", table_name="device_logs")
    op.drop_table("device_logs")
