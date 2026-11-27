"""SQLAlchemy user behavior repository."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from agentic_commerce_platform.domain.agent_models import UserBehaviorRecord
from agentic_commerce_platform.domain.data_models import BehaviorEvent
from agentic_commerce_platform.domain.enums import BehaviorType, DataSource
from agentic_commerce_platform.infrastructure.database.models import (
    UserBehaviorORM,
    UserORM,
)
from agentic_commerce_platform.infrastructure.database.session import DatabaseManager

__all__ = ["DatabaseUserBehaviorRepository"]


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite's naive datetime values to UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class DatabaseUserBehaviorRepository:
    """Persistent append-only behavior history with aggregated profile reads."""

    def __init__(self, database: DatabaseManager) -> None:
        """Store the injected database manager."""
        self._database = database

    @property
    def source(self) -> DataSource:
        """Return database provenance."""
        return DataSource.DATABASE

    def get_recent_behaviors(
        self,
        user_id: str,
        *,
        behavior_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[BehaviorEvent]:
        """Return recent behavior events, newest first."""
        if not user_id.strip():
            raise ValueError("user_id must not be blank")
        statement = select(UserBehaviorORM).where(UserBehaviorORM.user_id == user_id)
        if behavior_type:
            statement = statement.where(UserBehaviorORM.behavior_type == behavior_type)
        if since is not None:
            statement = statement.where(UserBehaviorORM.occurred_at >= since)
        statement = statement.order_by(
            UserBehaviorORM.occurred_at.desc(), UserBehaviorORM.id.desc()
        ).limit(limit)
        with self._database.session() as session:
            records = session.scalars(statement).all()
        return [self._to_domain(record) for record in records]

    def record_behavior(self, event: BehaviorEvent) -> BehaviorEvent:
        """Persist one event, creating the user if necessary."""
        with self._database.session() as session:
            user = session.scalar(
                select(UserORM.id).where(UserORM.user_id == event.user_id)
            )
            if user is None:
                session.add(UserORM(user_id=event.user_id))
                session.flush()
            record = UserBehaviorORM(
                user_id=event.user_id,
                behavior_type=event.behavior_type.value,
                item_id=event.item_id,
                category=event.category,
                amount=event.amount,
                metadata_json=event.metadata,
                occurred_at=event.occurred_at,
            )
            session.add(record)
            session.flush()
            return self._to_domain(record)

    def get_behavior(self, user_id: str) -> UserBehaviorRecord | None:
        """Aggregate recent historical events into the profile-agent input shape."""
        events = self.get_recent_behaviors(user_id, limit=100)
        if not events:
            return None
        category_counts: dict[str, int] = {}
        views: list[str] = []
        clicks: list[str] = []
        purchases: list[str] = []
        purchase_amounts: list[Decimal] = []
        for event in events:
            if event.item_id:
                if event.behavior_type is BehaviorType.VIEW:
                    views.append(event.item_id)
                elif event.behavior_type is BehaviorType.CLICK:
                    clicks.append(event.item_id)
                else:
                    purchases.append(event.item_id)
                    if event.amount is not None:
                        purchase_amounts.append(event.amount)
            if event.category:
                category_counts[event.category] = category_counts.get(event.category, 0) + 1

        latest = max(event.occurred_at for event in events)
        with self._database.session() as session:
            created_at = session.scalar(
                select(UserORM.created_at).where(UserORM.user_id == user_id)
            )
        now = datetime.now(UTC)
        account_age_days = (
            max(0, (now - _as_utc(created_at)).days) if created_at is not None else None
        )
        average_order_value = (
            sum(purchase_amounts, Decimal("0")) / len(purchase_amounts)
            if purchase_amounts
            else None
        )
        return UserBehaviorRecord(
            user_id=user_id,
            recent_views=list(dict.fromkeys(views))[:100],
            recent_clicks=list(dict.fromkeys(clicks))[:100],
            recent_purchases=list(dict.fromkeys(purchases))[:100],
            category_counts=category_counts,
            average_order_value=average_order_value,
            days_since_last_active=max(0, (now - latest).days),
            account_age_days=account_age_days,
        )

    @staticmethod
    def _to_domain(record: UserBehaviorORM) -> BehaviorEvent:
        """Map an ORM behavior row to a domain event."""
        return BehaviorEvent(
            user_id=record.user_id,
            behavior_type=BehaviorType(record.behavior_type),
            item_id=record.item_id,
            category=record.category,
            amount=record.amount,
            metadata=dict(record.metadata_json or {}),
            occurred_at=_as_utc(record.occurred_at),
        )
