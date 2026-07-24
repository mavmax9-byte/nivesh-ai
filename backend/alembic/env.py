"""Alembic migration environment.

Runs synchronously (psycopg2) even though the application runs async
(asyncpg) -- Alembic does not execute inside an event loop, per
docs/db 08-Database-Design.md's migration-strategy note in spirit.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import every domain module's models so Base.metadata is fully populated
# before autogenerate compares it against the live schema.
from nivesh.companies import models as companies_models  # noqa: F401
from nivesh.config import get_settings
from nivesh.core.db import Base
from nivesh.market_data import models as market_data_models  # noqa: F401
from nivesh.portfolios import models as portfolios_models  # noqa: F401
from nivesh.research import models as research_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.SYNC_DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
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
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
