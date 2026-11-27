"""Shared helpers for phase-four database, retrieval, and memory tests."""

from __future__ import annotations

from pathlib import Path

from agentic_commerce_platform.infrastructure.database import DatabaseManager
from agentic_commerce_platform.infrastructure.database.seed import seed_demo_database
from agentic_commerce_platform.settings import Settings


def make_database(tmp_path: Path, *, seed: bool = True) -> DatabaseManager:
    """Create an isolated SQLite database, optionally seeded with demo data."""
    database = DatabaseManager(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    database.create_schema()
    if seed:
        seed_demo_database(database)
    return database


def make_real_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Create phase-four Settings pointing at an isolated SQLite database."""
    values: dict[str, object] = {
        "_env_file": None,
        "app_name": "agentic-commerce-platform",
        "app_version": "0.1.0",
        "app_env": "test",
        "debug": False,
        "log_level": "ERROR",
        "llm_provider": "mock",
        "llm_api_key": "",
        "use_real_adapters": True,
        "database_url": f"sqlite:///{(tmp_path / 'api.db').as_posix()}",
        "seed_demo_data": True,
        "redis_enabled": False,
        "embedding_provider": "deterministic",
        "embedding_model": "deterministic-hash-v1",
        "embedding_dimensions": 64,
        "retrieval_score_threshold": 0.0,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]
