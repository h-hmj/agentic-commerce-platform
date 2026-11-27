"""SQLAlchemy declarative base and timestamp helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import DeclarativeBase

__all__ = ["Base", "utc_now"]


class Base(DeclarativeBase):
    """Declarative base for all phase-four ORM tables."""


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)
