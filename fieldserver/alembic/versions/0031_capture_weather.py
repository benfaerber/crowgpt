"""capture_weather — the hour's sky, joined to every real recording

The activity-prediction thread (FUTURE.txt, 2026-08-20) needs weather joined
to field recordings, and the join is free to collect now and archaeology to
reconstruct later. One row per enriched capture: the hour's conditions at the
capture's own coordinates, from Open-Meteo's archive.

Its own table rather than columns on captures: the enrichment is server-side
tooling (tools/enrich_weather.py), arrives hours-to-days after the capture,
and must never be mistaken for something the phone said. Nothing on the wire
changes — the phone neither sends nor sees weather.

KEPT CAPTURES ONLY by default, and that is the standing corpus lesson: a
seeded archive clip from another continent would join to plausible-looking
Salt Lake weather, and an analysis that forgot to filter keep would inherit
meteorological garbage that looks like data.

Revision ID: 0031_capture_weather
Revises: 0030_capture_trigger
"""

import sqlalchemy as sa
from alembic import op

revision = "0031_capture_weather"
down_revision = "0030_capture_trigger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "capture_weather" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "capture_weather",
        sa.Column("capture_id", sa.Integer(),
                  sa.ForeignKey("captures.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("temp_c", sa.Float()),
        sa.Column("wind_kmh", sa.Float()),
        sa.Column("gust_kmh", sa.Float()),
        sa.Column("precip_mm", sa.Float()),
        sa.Column("cloud_pct", sa.Integer()),
        sa.Column("pressure_hpa", sa.Float()),
        # Which provider and when it was asked, so a re-enrichment can say
        # what it replaced.
        sa.Column("source", sa.Text(), nullable=False,
                  server_default="open-meteo"),
        sa.Column("fetched_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("capture_weather")
