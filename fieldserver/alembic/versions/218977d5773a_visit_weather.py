"""visit weather

Scout-visit marks are the labels the 0084 scoring will one day be fitted
against, and Ben's first two nulls fell inside a 38 °C afternoon — outcome
without conditions is half a label. Same shape and reasoning as 0031's
capture_weather: joined after the fact from the archive API off the visit's
own GPS and time, so it needs nothing from the phone and works
retroactively. All visits qualify (unlike captures there is no seeded
noise to fence off).

Revision ID: 218977d5773a
Revises: 0032_scout_visits
"""

from alembic import op
import sqlalchemy as sa


revision = '218977d5773a'
down_revision = '0032_scout_visits'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visit_weather",
        sa.Column("visit_id", sa.Integer(),
                  sa.ForeignKey("scout_visits.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("temp_c", sa.Float()),
        sa.Column("wind_kmh", sa.Float()),
        sa.Column("gust_kmh", sa.Float()),
        sa.Column("precip_mm", sa.Float()),
        sa.Column("cloud_pct", sa.Integer()),
        sa.Column("pressure_hpa", sa.Float()),
        sa.Column("source", sa.Text(), nullable=False,
                  server_default="open-meteo"),
        sa.Column("fetched_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    raise NotImplementedError("not reversible")
