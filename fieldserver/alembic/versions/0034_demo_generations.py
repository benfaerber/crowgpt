"""generations learn who asked — the chat, or a visitor to the promo page

The promo's "ask it yourself" buttons draw from a pool of clips the worker
generates ahead of time, so a visitor hears something at once on a box that
takes half a minute a bout. Three columns tell those rows apart from the
dashboard's chat and let the pool be managed in place of a second table:

  source     'chat' for Crow Chat, 'demo' for the promo pool. The chat lists
             only its own rows; the demo serves only its own.
  priority   what the worker picks first. A visitor or operator waiting on a
             clip is 1; a refill nobody is waiting for is 0.
  served_at  when a demo row was handed to a visitor. NULL means it is still
             on the shelf.

Revision ID: 0034_demo_generations
Revises: 0033_access_requests
"""

import sqlalchemy as sa
from alembic import op

revision = "0034_demo_generations"
down_revision = "0033_access_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("generations") as batch:
        batch.add_column(sa.Column("source", sa.Text(), nullable=False,
                                   server_default="chat"))
        batch.add_column(sa.Column("priority", sa.Integer(), nullable=False,
                                   server_default="0"))
        batch.add_column(sa.Column("served_at", sa.Text()))
    # Every row so far was somebody at the chat waiting for an answer.
    op.execute("UPDATE generations SET priority = 1")
    op.create_index("ix_generations_source_state", "generations",
                    ["source", "state"])


def downgrade() -> None:
    op.drop_index("ix_generations_source_state", table_name="generations")
    with op.batch_alter_table("generations") as batch:
        batch.drop_column("served_at")
        batch.drop_column("priority")
        batch.drop_column("source")
