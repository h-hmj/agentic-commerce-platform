"""The checked-in Alembic migration creates the phase-four schema."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_creates_phase4_tables(tmp_path, monkeypatch) -> None:
    """Migration is executable against a fresh SQLite URL."""
    root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "migrated.db"
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite:///{database_path.as_posix()}",
    )
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert {
        "products",
        "inventory_records",
        "users",
        "user_behaviors",
        "user_profiles",
        "product_embeddings",
        "alembic_version",
    } <= tables
