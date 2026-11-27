"""SQLAlchemy user identity repository."""

from __future__ import annotations

from sqlalchemy import select

from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.infrastructure.database.models import UserORM
from agentic_commerce_platform.infrastructure.database.session import DatabaseManager

__all__ = ["DatabaseUserRepository"]


class DatabaseUserRepository:
    """Ensure and query minimal persistent user records."""

    def __init__(self, database: DatabaseManager) -> None:
        """Store the injected database manager."""
        self._database = database

    @property
    def source(self) -> DataSource:
        """Return database provenance."""
        return DataSource.DATABASE

    def ensure_user(self, user_id: str) -> None:
        """Create a user row if it does not already exist."""
        if not user_id.strip():
            raise ValueError("user_id must not be blank")
        with self._database.session() as session:
            existing = session.scalar(select(UserORM.id).where(UserORM.user_id == user_id))
            if existing is None:
                session.add(UserORM(user_id=user_id))

    def exists(self, user_id: str) -> bool:
        """Return whether a persistent user exists."""
        with self._database.session() as session:
            return session.scalar(select(UserORM.id).where(UserORM.user_id == user_id)) is not None
