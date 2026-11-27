"""Database engine/session lifecycle without global session objects."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from agentic_commerce_platform.infrastructure.database.base import Base

__all__ = ["DatabaseManager"]


class DatabaseManager:
    """Own the SQLAlchemy engine and short-lived session factory.

    Repositories receive this manager (or a session factory) through dependency
    injection. No module-level Session or Engine is shared.
    """

    def __init__(self, database_url: str, *, echo: bool = False) -> None:
        """Create an engine and session factory for the configured database URL."""
        if not database_url.strip():
            raise ValueError("database_url must not be blank")

        url = make_url(database_url)
        if url.get_backend_name() == "sqlite" and url.database not in (None, ":memory:"):
            Path(url.database).expanduser().resolve().parent.mkdir(
                parents=True,
                exist_ok=True,
            )

        connect_args = (
            {"check_same_thread": False} if url.get_backend_name() == "sqlite" else {}
        )
        self._engine: Engine = create_engine(
            database_url,
            echo=echo,
            future=True,
            connect_args=connect_args,
            pool_pre_ping=url.get_backend_name() != "sqlite",
        )
        self._session_factory = sessionmaker(
            bind=self._engine,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )

    @property
    def engine(self) -> Engine:
        """Return the engine for schema inspection/testing."""
        return self._engine

    def create_schema(self) -> None:
        """Create missing tables; production deployments may use Alembic instead."""
        Base.metadata.create_all(self._engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a session and guarantee rollback/close on failure."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Dispose of pooled connections."""
        self._engine.dispose()
