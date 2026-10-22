"""scout_visits — where somebody actually went, and what they found

The 0084 scouting score is a prior graded by boots; this table is the boots.
One row per marked spot: a tree or target tapped on the app's map, an
outcome, the spot's coordinates and the moment. These rows are the labels
that eventually re-weight the score — which is why "nothing" is a
first-class outcome, not an absence: a visited target with no crows is worth
exactly as much to the re-weighting as one with them.

Attached to no capture on purpose. A visit is about a place; if a capture
happens there too, the GPS join at analysis time is honest and free, where a
foreign key would force every mark to invent a recording.

Revision ID: 0032_scout_visits
Revises: 0031_capture_weather
"""

import sqlalchemy as sa
from alembic import op

revision = "0032_scout_visits"
down_revision = "0031_capture_weather"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "scout_visits" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "scout_visits",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Idempotency, as everywhere on the sync path: a retried push must
        # land once.
        sa.Column("client_uuid", sa.Text(), nullable=False, unique=True),
        sa.Column("contributor_id", sa.Integer(),
                  sa.ForeignKey("contributors.id")),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id")),
        # What was tapped: 'tree' or 'target' today; free text so a future
        # layer needs no migration.
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        # 'crows' or 'nothing' today; free text for the same reason as kind.
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        # When the recordist stood there, by the phone's clock — distinct
        # from created_at, which is when the row reached this server.
        sa.Column("visited_at", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("ix_scout_visits_visited", "scout_visits", ["visited_at"])


def downgrade() -> None:
    op.drop_table("scout_visits")
