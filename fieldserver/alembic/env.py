"""Alembic environment for the field server.

No SQLAlchemy models: the schema is defined by the migrations themselves and
queried with plain SQL everywhere else. Alembic is here for the ledger and for
`batch_alter_table`, which rewrites a SQLite table so a constraint can change —
the operation SQLite has no ALTER for, and the one that has bitten this project
twice.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from fieldserver.core.paths import database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Only when the caller has not already said which database. Overwriting it
# unconditionally meant a programmatic caller asking for a throwaway reference
# database silently got the live one instead — which is how a schema check
# nearly ran the baseline over real captures.
if not config.get_main_option("sqlalchemy.url", None):
    config.set_main_option("sqlalchemy.url", database_url())

# Nothing to autogenerate against, by design.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        # SQLite cannot ALTER most things in place, so every op goes through a
        # table rebuild. Setting it here means a migration author never has to
        # remember which operations need it.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
