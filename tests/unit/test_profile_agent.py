"""Tests for UserProfileAgent's deterministic rules and LLM fallback."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from agentic_commerce_platform.agents.profile_agent import UserProfileAgent
from agentic_commerce_platform.domain.agent_models import (
    UserBehaviorRecord,
    UserProfileInput,
    UserProfileOutput,
)
from agentic_commerce_platform.domain.enums import DataSource, ProfileSource, UserSegment
from agentic_commerce_platform.infrastructure.data import InMemoryUserBehaviorRepository
from agentic_commerce_platform.infrastructure.llm import MockLLMProvider
from tests.helpers import parse_output


def _repository(*records: UserBehaviorRecord) -> InMemoryUserBehaviorRepository:
    return InMemoryUserBehaviorRepository(records)


async def test_profile_from_normal_behavior_data() -> None:
    """Rule-derived facts and a mock explanation are both returned."""
    record = UserBehaviorRecord(
        user_id="u-1",
        recent_views=["p-1", "p-2", "p-8"],
        recent_clicks=["p-1"],
        recent_purchases=["p-1"],
        category_counts={"books": 3, "electronics": 1},
        average_order_value=Decimal("680.00"),
        days_since_last_active=2,
        account_age_days=200,
    )
    agent = UserProfileAgent(_repository(record), MockLLMProvider())

    result = await agent.run(request=UserProfileInput(user_id="u-1"))
    output = parse_output(result, UserProfileOutput)

    assert result.agent_name == "user_profile_agent"
    assert result.confidence == output.confidence
    assert output.user_id == "u-1"
    assert UserSegment.ACTIVE in output.segments
    assert UserSegment.HIGH_VALUE in output.segments
    assert output.preferred_categories == ["books", "electronics"]
    assert output.price_range.min_price == Decimal("476.00")
    assert output.price_range.max_price == Decimal("884.00")
    assert output.recent_interests == ["p-1", "p-2", "p-8"]
    assert output.profile_source is ProfileSource.RULE_BASED_AND_MOCK_LLM
    assert output.data_source is DataSource.IN_MEMORY_DEMO
    assert "MOCK" in (output.explanation or "")
    assert output.warnings == []


async def test_empty_behavior_returns_reasonable_new_user_default() -> None:
    """Unknown users receive a rule-derived default, not invented facts."""
    agent = UserProfileAgent(
        InMemoryUserBehaviorRepository([]),
        MockLLMProvider(),
    )

    result = await agent.run(request=UserProfileInput(user_id="u-empty"))
    output = parse_output(result, UserProfileOutput)

    assert output.segments == [UserSegment.NEW_USER]
    assert output.preferred_categories == []
    assert output.price_range.min_price == Decimal("0")
    assert output.price_range.max_price is None
    assert output.recent_interests == []
    assert output.confidence == 0.2
    assert output.data_source is DataSource.IN_MEMORY_DEMO


async def test_new_user_identification() -> None:
    """A recently created account with little activity is a new user."""
    record = UserBehaviorRecord(
        user_id="u-new",
        recent_views=["p-1"],
        account_age_days=2,
        days_since_last_active=1,
    )
    agent = UserProfileAgent(_repository(record), MockLLMProvider())

    output = parse_output(
        await agent.run(request=UserProfileInput(user_id="u-new")),
        UserProfileOutput,
    )

    assert UserSegment.NEW_USER in output.segments
    assert UserSegment.HIGH_VALUE not in output.segments


async def test_active_user_identification() -> None:
    """Recent multi-step activity identifies an active user."""
    record = UserBehaviorRecord(
        user_id="u-active",
        recent_views=["p-1", "p-2", "p-3"],
        recent_clicks=["p-1", "p-2"],
        category_counts={"books": 2},
        average_order_value=Decimal("250.00"),
        days_since_last_active=1,
        account_age_days=100,
    )
    agent = UserProfileAgent(_repository(record), MockLLMProvider())

    output = parse_output(
        await agent.run(request=UserProfileInput(user_id="u-active")),
        UserProfileOutput,
    )

    assert UserSegment.ACTIVE in output.segments
    assert UserSegment.NEW_USER not in output.segments


async def test_price_sensitive_user_identification() -> None:
    """A low historical average order value marks price sensitivity."""
    record = UserBehaviorRecord(
        user_id="u-value",
        recent_views=["p-1", "p-2", "p-3"],
        recent_clicks=["p-1", "p-2"],
        recent_purchases=["p-3"],
        category_counts={"travel": 3},
        average_order_value=Decimal("60.00"),
        days_since_last_active=2,
        account_age_days=90,
    )
    agent = UserProfileAgent(_repository(record), MockLLMProvider())

    output = parse_output(
        await agent.run(request=UserProfileInput(user_id="u-value")),
        UserProfileOutput,
    )

    assert UserSegment.PRICE_SENSITIVE in output.segments
    assert UserSegment.HIGH_VALUE not in output.segments


async def test_high_value_and_churn_segments() -> None:
    """High spend and inactivity signals are independently testable."""
    high_value = UserBehaviorRecord(
        user_id="u-high",
        recent_views=["p-1", "p-2", "p-3"],
        recent_purchases=["p-1", "p-2"],
        category_counts={"electronics": 2},
        average_order_value=Decimal("900.00"),
        days_since_last_active=1,
        account_age_days=300,
    )
    churn = UserBehaviorRecord(
        user_id="u-churn",
        recent_views=["p-1"],
        recent_clicks=["p-1"],
        recent_purchases=["p-1"],
        category_counts={"home": 1},
        average_order_value=Decimal("300.00"),
        days_since_last_active=45,
        account_age_days=500,
    )
    repository = _repository(high_value, churn)

    high_output = parse_output(
        await UserProfileAgent(repository, MockLLMProvider()).run(
            request=UserProfileInput(user_id="u-high")
        ),
        UserProfileOutput,
    )
    churn_output = parse_output(
        await UserProfileAgent(repository, MockLLMProvider()).run(
            request=UserProfileInput(user_id="u-churn")
        ),
        UserProfileOutput,
    )

    assert UserSegment.HIGH_VALUE in high_output.segments
    assert UserSegment.CHURN_RISK in churn_output.segments
    assert UserSegment.ACTIVE not in churn_output.segments


async def test_mock_llm_failure_degrades_to_rule_based_profile() -> None:
    """An explanation failure must not fail the structured profile."""
    record = UserBehaviorRecord(
        user_id="u-1",
        recent_views=["p-1"],
        category_counts={"books": 1},
        days_since_last_active=3,
        account_age_days=20,
    )
    agent = UserProfileAgent(
        _repository(record),
        MockLLMProvider(fail=True, failure_message="mock explanation unavailable"),
    )

    result = await agent.run(request=UserProfileInput(user_id="u-1"))
    output = parse_output(result, UserProfileOutput)

    assert result.success is True
    assert output.profile_source is ProfileSource.RULE_BASED
    assert output.explanation is None
    assert output.warnings == ["mock_llm_unavailable"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"user_id": ""},
        {"user_id": "u-1", "category_counts": {"books": -1}},
        {"user_id": "u-1", "average_order_value": Decimal("-1")},
        {"user_id": "u-1", "days_since_last_active": -1},
    ],
)
def test_profile_input_rejects_invalid_values(kwargs: dict[str, object]) -> None:
    """Invalid behavior input fails Pydantic validation before execution."""
    with pytest.raises(ValidationError):
        UserProfileInput(**kwargs)


async def test_repository_failure_returns_structured_agent_failure() -> None:
    """Repository exceptions are surfaced as failed AgentResult values."""

    class BrokenRepository:
        @property
        def source(self) -> DataSource:
            return DataSource.IN_MEMORY_DEMO

        def get_behavior(self, user_id: str) -> UserBehaviorRecord | None:
            raise RuntimeError("behavior store unavailable")

    agent = UserProfileAgent(BrokenRepository(), MockLLMProvider())

    result = await agent.run(request=UserProfileInput(user_id="u-1"))

    assert result.success is False
    assert result.error is not None
    assert "behavior store unavailable" in result.error
