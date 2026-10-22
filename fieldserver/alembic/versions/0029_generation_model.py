"""generations pick a model — the chat can address a release, not just model-calltype

The model becomes part of the request, chosen at enqueue like the seed, so an
exchange is reproducible from its row alone even after the default changes.
Until now `model` was reply-side provenance the worker wrote at completion;
every existing row was answered by model-calltype, so the backfill states that
and the column turns NOT NULL.

`call_type` loses its NOT NULL because the releases (CrowGPT1, CrowGPT2) carry
no call types in their manifests — a request addressed to one is a bare "caw,
please", and NULL is that request, not a missing value.

Revision ID: 0029_generation_model
Revises: 0028_generations
"""

import sqlalchemy as sa
from alembic import op

revision = "0029_generation_model"
down_revision = "0028_generations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE generations SET model = 'model-calltype' WHERE model IS NULL")
    with op.batch_alter_table("generations") as batch:
        batch.alter_column("call_type", existing_type=sa.Text(), nullable=True)
        batch.alter_column("model", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    """Queued release requests would become NOT NULL violations, not data."""
    raise NotImplementedError("not reversible")
