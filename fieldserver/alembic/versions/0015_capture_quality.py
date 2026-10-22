"""a quality row per capture — measurements, not opinions

Nothing on a capture says how hard it was to hear. Experiment 0008 had to
measure the lawn mower off the spectrum after the fact and the number went
nowhere, so the next question about noise starts from scratch. This table is
where those numbers live from now on: written by the worker when it analyses,
backfillable over the whole corpus because it needs nothing from the recordist.

Deliberately NOT an entry in the label vocabulary. `label_defs` carries
`core_mapping`, so everything in it is a claim about what a call *is* and
trains something. "Noisy" is a property of the recording, measured rather than
judged, and putting it there would either train nothing or train noise as a
call type.

One row per capture, keyed on the capture itself, because quality is a property
of the audio and not of the model version — re-analysis overwrites rather than
accumulates. `media_id` records which file was measured; it goes when the file
goes, since the quality of a deleted recording is about nothing.

The columns are the calibrated set, and their meaning is pinned to the
experiments: `band_snr_db` is 0004's axis (~2.5 dB costs ~0.19 of BirdNET
confidence, `analyzer/quality.py` holds the byte-identical function), the two
noise floors are 0008's finding that absolute level in the crow band answers
masking while spectral fractions answer nothing, and `clip_events` alongside
`clipped_samples` is 0009's lesson that 195 clipped samples can be two knocks.

Backfill is a tool, not this migration — 0009_pcm_sha256 set that precedent:
decoding every file in the corpus is a job for `tools/backfill_quality.py`,
run watched, in the venv that has the DSP libraries.

Revision ID: 0015_capture_quality
Revises: 0014_label_revisions
"""

import sqlalchemy as sa
from alembic import op

revision = "0015_capture_quality"
down_revision = "0014_label_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "capture_quality" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "capture_quality",
        sa.Column("capture_id", sa.Integer(),
                  sa.ForeignKey("captures.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("media_id", sa.Integer(),
                  sa.ForeignKey("media.id", ondelete="CASCADE"),
                  nullable=False),
        # Nullable, alone among the measures, and found rather than designed:
        # a merged capture holds digital zero in the gaps between its parts, so
        # the quiet percentile the SNR divides by is exactly 0 and the ratio is
        # infinity — which is not a number, and not JSON either. The floors and
        # levels carry epsilons and stay finite; the SNR is a ratio and cannot.
        # NULL means "no quiet signal to measure against", not "unmeasured".
        sa.Column("band_snr_db", sa.Float(), nullable=True),
        sa.Column("noise_floor_low_dbfs", sa.Float(), nullable=False),
        sa.Column("noise_floor_band_dbfs", sa.Float(), nullable=False),
        sa.Column("peak_dbfs", sa.Float(), nullable=False),
        sa.Column("rms_dbfs", sa.Float(), nullable=False),
        sa.Column("clipped_samples", sa.Integer(), nullable=False),
        sa.Column("clip_events", sa.Integer(), nullable=False),
        sa.Column("measured_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    # Unlike 0014, dropping this loses nothing that cannot be recomputed:
    # the audio is the source of truth and the backfill tool rebuilds the table.
    op.drop_table("capture_quality")
