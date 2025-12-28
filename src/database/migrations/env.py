"""Alembic migration environment configuration."""

from logging.config import fileConfig
import sys
import os

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

# Import application config and models
from src.config import settings
from src.models.db_models import Base

# Alembic Config object provides access to alembic.ini values
config = context.config

# Override sqlalchemy.url with environment variable
# Escape % characters for ConfigParser (% becomes %%)
database_url = settings.database_url.replace("%", "%%")
config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging if it exists
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add model's MetaData object for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well. By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_schemas=False,
            render_as_batch=False,
        )

        with context.begin_transaction():
            context.run_migrations()


# Determine which mode to run in
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
