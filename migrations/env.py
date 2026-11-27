"""Alembic environment for the phase-four SQLAlchemy schema."""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from agentic_commerce_platform.infrastructure.database.base import Base
from agentic_commerce_platform.infrastructure.database import models  # noqa: F401
from agentic_commerce_platform.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

database_url = os.getenv("DATABASE_URL") or get_settings().database_url
config.set_main_option("sqlalchemy.url", database_url)

url = make_url(config.get_main_option("sqlalchemy.url"))
if url.get_backend_name() == "sqlite" and url.database not in (None, ":memory:"):
    Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without a database connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations using a short-lived SQLAlchemy engine."""
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
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
