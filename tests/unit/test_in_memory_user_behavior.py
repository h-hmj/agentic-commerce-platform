"""Tests for the in-memory user behavior adapter."""

from __future__ import annotations

from decimal import Decimal

import pytest

from agentic_commerce_platform.domain.agent_models import UserBehaviorRecord
from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.infrastructure.data import InMemoryUserBehaviorRepository


def _record(user_id: str = "u-1") -> UserBehaviorRecord:
    return UserBehaviorRecord(
        user_id=user_id,
        recent_views=["p-1"],
        category_counts={"books": 1},
        average_order_value=Decimal("99.00"),
    )


def test_behavior_lookup_returns_copy() -> None:
    """Mutating a returned record does not alter repository state."""
    repository = InMemoryUserBehaviorRepository([_record()])

    first = repository.get_behavior("u-1")
    assert first is not None
    first.recent_views.append("p-2")

    second = repository.get_behavior("u-1")

    assert second is not None
    assert second.recent_views == ["p-1"]
    assert repository.source is DataSource.IN_MEMORY_DEMO


def test_unknown_user_returns_none() -> None:
    """Unknown users return None rather than fabricated behavior."""
    repository = InMemoryUserBehaviorRepository([_record()])

    assert repository.get_behavior("unknown") is None


def test_duplicate_user_records_are_rejected() -> None:
    """Duplicate records fail fast because lookup would be ambiguous."""
    with pytest.raises(ValueError, match="duplicate user behavior"):
        InMemoryUserBehaviorRepository([_record(), _record()])


def test_demo_behavior_records_are_deterministic() -> None:
    """The default records are stable phase-two in-memory demo data."""
    repository = InMemoryUserBehaviorRepository()

    record = repository.get_behavior("u-demo-001")

    assert record is not None
    assert record.average_order_value == Decimal("680.00")
    assert repository.source is DataSource.IN_MEMORY_DEMO
