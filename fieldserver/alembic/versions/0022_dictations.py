"""dictations — a spoken field note, its transcript, and the queue that makes one

Labelling is the bottleneck everything else waits on, and the `label-set` skill
never listens to audio: every fact in it comes from the recordist's answers,
recalled hours later at a desk. A dictation is those same answers taken in the
field, seconds after the birds did the thing. That is the difference between "I
think two of them were mobbing" and what actually happened.

TWO TABLES IN ONE REVISION, because a job table without the artifact it works on
is not a state worth being able to reach.

WHY NOT A `media` ROW, which is the obvious shortcut. `MediaStore.complete_audio_for`
does not filter by kind — it only *sorts* (`ORDER BY CASE kind WHEN 'audio' THEN 0
ELSE 1 END, id DESC`), so every complete media row is a candidate and among
non-audio kinds the newest wins. A dictation filed there would be handed to BirdNET
whenever a capture's own audio had not finished uploading, and would become the
default `media_id` for a label. A human voice track counted as field audio is a
worse version of the problem the ★ Keep flag already exists to hold back.

The bytes live in `instance/dictations/`, never `instance/media/`, so the media
directory's invariant stays literally true: everything in it is somebody's actual
recording of birds. That also turns retention into a fact about a folder rather
than a predicate scattered across the corpus — which matters, because a memo is
speech, may name people and places, and syncs to a server with no TLS and one
shared secret.

WHY `transcript` IS NOT AN OBSERVATION. `observations.source` has had a 'voice'
value since the baseline, and writing Whisper's output straight there is tempting
and wrong: `label-set` renders observations under "WHAT THE RECORDIST WROTE (weigh
this above the model)" with no hedge and without even selecting `source`. A
mis-heard crow name or head count would be indistinguishable from testimony
forever, and names and counts are exactly what speech recognition gets wrong. So
the transcript stays here as raw machine output, and a human reading it is what
promotes it into an `observations` row — `confirmed_at` and `observation_id`
record that that happened.

Revision ID: 0022_dictations
Revises: f91099fdc60a
"""

import sqlalchemy as sa
from alembic import op

revision = "0022_dictations"
down_revision = "f91099fdc60a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()

    if "dictations" not in tables:
        op.create_table(
            "dictations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("capture_id", sa.Integer(),
                      sa.ForeignKey("captures.id", ondelete="CASCADE"), nullable=False),
            sa.Column("contributor_id", sa.Integer(), sa.ForeignKey("contributors.id")),
            sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id")),
            # Idempotency key, as on media and observations: a retried sync must
            # resume the upload it started rather than strand a half-written file
            # behind a second row.
            sa.Column("client_uuid", sa.Text()),
            # The same seam media uses: apartment disk now, object storage later.
            sa.Column("storage", sa.Text(), nullable=False, server_default="local"),
            sa.Column("storage_ref", sa.Text(), nullable=False),
            sa.Column("format", sa.Text(), nullable=False, server_default="wav"),
            sa.Column("sample_rate", sa.Integer()),
            sa.Column("channels", sa.Integer()),
            sa.Column("bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sha256", sa.Text()),
            sa.Column("upload_state", sa.Text(), nullable=False, server_default="pending"),
            sa.Column("duration_sec", sa.Float()),
            # When he spoke, which is not when the capture was recorded — the memo
            # comes after the event and the gap between them is worth keeping.
            sa.Column("recorded_at", sa.Text()),
            # What the phone thought was being spoken. A hint for the decode to
            # disagree with and log, never the decision.
            sa.Column("locale", sa.Text()),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("uploaded_at", sa.Text()),
            # Raw machine output. Never testimony — see the docstring.
            sa.Column("transcript", sa.Text()),
            sa.Column("transcript_model", sa.Text()),
            sa.Column("transcript_language", sa.Text()),
            sa.Column("transcribed_at", sa.Text()),
            # Whisper's own confidence proxy, so a bad decode is visible in the
            # data rather than only to somebody reading the words.
            sa.Column("mean_logprob", sa.Float()),
            sa.Column("confirmed_at", sa.Text()),
            sa.Column("confirmed_by", sa.Integer(), sa.ForeignKey("contributors.id")),
            # SET NULL, not CASCADE: deleting the promoted note is the recordist
            # retracting what he wrote, not a reason to lose the recording of him
            # saying it.
            sa.Column("observation_id", sa.Integer(),
                      sa.ForeignKey("observations.id", ondelete="SET NULL")),
        )
        op.create_index("ix_dictations_capture", "dictations", ["capture_id"])
        op.create_index("ux_dictations_capture_client_uuid", "dictations",
                        ["capture_id", "client_uuid"], unique=True)

    if "dictation_jobs" not in tables:
        op.create_table(
            "dictation_jobs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("dictation_id", sa.Integer(),
                      sa.ForeignKey("dictations.id", ondelete="CASCADE"), nullable=False),
            # Denormalised so a job can be authorised without joining. The
            # analysis queue learned that the hard way — see api/analysis.py.
            sa.Column("capture_id", sa.Integer(),
                      sa.ForeignKey("captures.id", ondelete="CASCADE"), nullable=False),
            sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
            # Present from the start, unlike analysis_jobs which needed 0017 to
            # add it. Without it `reclaim_running` cannot tell a job that crashed
            # the worker once from one that will crash it every restart.
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("claimed_at", sa.Text()),
            sa.Column("finished_at", sa.Text()),
            sa.Column("error", sa.Text()),
            sa.Column("created_at", sa.Text(), nullable=False),
        )
        op.create_index("ix_dictation_jobs_state", "dictation_jobs", ["state"])


def downgrade() -> None:
    """Drops both tables, and with them every transcript.

    The audio itself survives in `instance/dictations/` with nothing pointing at
    it, which is worse than a clean loss: it is a directory of unattributed
    recordings of somebody talking. A development action only.
    """
    op.drop_table("dictation_jobs")
    op.drop_table("dictations")
