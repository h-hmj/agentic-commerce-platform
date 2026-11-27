"""SQLAlchemy user profile persistence repository."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select

from agentic_commerce_platform.domain.agent_models import PriceRange, UserProfileOutput
from agentic_commerce_platform.domain.data_models import PersistedUserProfile
from agentic_commerce_platform.domain.enums import DataSource, ProfileSource, UserSegment
from agentic_commerce_platform.infrastructure.database.models import (
    UserORM,
    UserProfileORM,
)
from agentic_commerce_platform.infrastructure.database.session import DatabaseManager

__all__ = ["DatabaseUserProfileRepository"]


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive datetime values to UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class DatabaseUserProfileRepository:
    """Insert/update persistent profile snapshots with source and timestamps."""

    def __init__(self, database: DatabaseManager) -> None:
        """Store the injected database manager."""
        self._database = database

    @property
    def source(self) -> DataSource:
        """Return database provenance."""
        return DataSource.DATABASE

    def get_profile(self, user_id: str) -> PersistedUserProfile | None:
        """Return the latest profile snapshot or ``None``."""
        with self._database.session() as session:
            record = session.scalar(
                select(UserProfileORM).where(UserProfileORM.user_id == user_id)
            )
            if record is None:
                return None
            return self._to_domain(record)

    def save_profile(self, profile: UserProfileOutput) -> PersistedUserProfile:
        """Insert or update a profile idempotently."""
        with self._database.session() as session:
            session.flush()
            user_exists = session.scalar(
                select(UserORM.id).where(UserORM.user_id == profile.user_id)
            )
            if user_exists is None:
                session.add(UserORM(user_id=profile.user_id))
                session.flush()
            record = session.scalar(
                select(UserProfileORM).where(
                    UserProfileORM.user_id == profile.user_id
                )
            )
            if record is None:
                record = UserProfileORM(user_id=profile.user_id)
                session.add(record)
            record.segments = [segment.value for segment in profile.segments]
            record.preferred_categories = list(profile.preferred_categories)
            record.price_min = profile.price_range.min_price
            record.price_max = profile.price_range.max_price
            record.recent_interests = list(profile.recent_interests)
            record.confidence = profile.confidence
            record.source = profile.profile_source.value
            record.memory_source = profile.memory_source
            record.explanation = profile.explanation
            record.warnings = list(profile.warnings)
            record.updated_at = datetime.now(UTC)
            session.flush()
            return self._to_domain(record)

    def invalidate(self, user_id: str) -> bool:
        """Delete a stored profile; return whether a record existed."""
        with self._database.session() as session:
            result = session.execute(
                delete(UserProfileORM).where(UserProfileORM.user_id == user_id)
            )
            return bool(result.rowcount)

    @staticmethod
    def _to_domain(record: UserProfileORM) -> PersistedUserProfile:
        """Map an ORM profile row to a domain profile snapshot."""
        profile = UserProfileOutput(
            user_id=record.user_id,
            segments=[UserSegment(value) for value in record.segments],
            preferred_categories=list(record.preferred_categories or []),
            price_range=PriceRange(
                min_price=record.price_min,
                max_price=record.price_max,
            ),
            recent_interests=list(record.recent_interests or []),
            confidence=record.confidence,
            profile_source=ProfileSource(record.source),
            data_source=DataSource.DATABASE,
            memory_source=record.memory_source,
            profile_persisted=True,
            explanation=record.explanation,
            warnings=list(record.warnings or []),
        )
        return PersistedUserProfile(profile=profile, updated_at=_as_utc(record.updated_at))
