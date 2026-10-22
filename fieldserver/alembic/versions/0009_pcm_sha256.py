"""a hash of the samples, not of the file

`media.sha256` hashes the stored bytes, which is exactly right for spotting a
corrupted upload and useless the moment the same audio can live in two
containers. Storing a capture as FLAC changes every byte and none of the sound.

So a second hash, taken from the decoded PCM. It survives re-containering,
which makes it the one a mover can verify a copy against before deleting an
original — the thing the VPS-to-NAS plan in TODO.txt turns on.

Nullable, and left empty for rows transcoded before this existed rather than
backfilled here: computing it means decoding every file, which is a job for a
script somebody runs and watches, not for a migration that runs at boot.

Revision ID: 0009_pcm_sha256
Revises: 0008_location_precision
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_pcm_sha256"
down_revision = "0008_location_precision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media", sa.Column("pcm_sha256", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("media") as batch:
        batch.drop_column("pcm_sha256")
