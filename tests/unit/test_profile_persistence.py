"""Profile source priority, memory cache, and database persistence tests."""

from __future__ import annotations

from decimal import Decimal

from datetime import datetime
from typing import Any

from agentic_commerce_platform.domain.agent_models import UserProfileInput
from agentic_commerce_platform.domain.data_models import BehaviorEvent
from agentic_commerce_platform.domain.enums import BehaviorType, DataSource
from agentic_commerce_platform.infrastructure.cache.memory_store import InMemoryMemoryStore
from agentic_commerce_platform.infrastructure.data import (
    InMemoryUserBehaviorRepository,
    InMemoryUserProfileRepository,
)
from agentic_commerce_platform.infrastructure.database.repositories import (
    DatabaseUserBehaviorRepository,
    DatabaseUserProfileRepository,
)
from agentic_commerce_platform.infrastructure.llm.mock_provider import MockLLMProvider
from agentic_commerce_platform.services.profile_service import ProfileService
from tests.phase4_helpers import make_database


def _service_with_memory() -> tuple[
    ProfileService, InMemoryMemoryStore, InMemoryUserProfileRepository
]:
    memory_store = InMemoryMemoryStore()
    profile_repository = InMemoryUserProfileRepository()
    service = ProfileService(
        InMemoryUserBehaviorRepository(),
        MockLLMProvider(),
        profile_repository=profile_repository,
        memory_store=memory_store,
    )
    return service, memory_store, profile_repository


async def test_profile_is_persisted_and_cache_is_used_second_time() -> None:
    """A built profile is persisted, then served from the memory cache."""
    service, _memory, profile_repository = _service_with_memory()

    first = await service.get_or_build_profile("u-demo-001")
    second = await service.get_or_build_profile("u-demo-001")

    assert first.profile_persisted is True
    assert first.data_source is DataSource.IN_MEMORY_DEMO
    assert profile_repository.get_profile("u-demo-001") is not None
    assert second.memory_source == "in_memory"
    assert second.user_id == "u-demo-001"


async def test_realtime_memory_beats_historical_and_persisted_data() -> None:
    """Recent Redis/in-memory events win when no explicit request behavior exists."""
    service, memory_store, _profile_repository = _service_with_memory()
    await memory_store.record_behavior(
        BehaviorEvent(
            user_id="u-new",
            behavior_type=BehaviorType.PURCHASE,
            item_id="p-002",
            category="electronics",
            amount=Decimal("1299.00"),
        )
    )

    profile = await service.get_or_build_profile("u-new")

    assert profile.data_source is DataSource.IN_MEMORY
    assert profile.memory_source == "in_memory"
    assert "electronics" in profile.preferred_categories
    assert profile.profile_persisted is True


async def test_explicit_behavior_overrides_realtime_memory() -> None:
    """Explicit request fields take precedence over memory events."""
    service, memory_store, _profile_repository = _service_with_memory()
    await memory_store.record_behavior(
        BehaviorEvent(
            user_id="u-explicit",
            behavior_type=BehaviorType.VIEW,
            item_id="p-001",
            category="books",
        )
    )

    profile = await service.get_or_build_profile(
        "u-explicit",
        explicit_input=UserProfileInput(
            user_id="u-explicit",
            category_counts={"electronics": 5},
            recent_purchases=["p-002"],
            average_order_value=Decimal("1500.00"),
            days_since_last_active=1,
            account_age_days=400,
        ),
    )

    assert profile.preferred_categories
    assert profile.preferred_categories[0] == "electronics"
    assert profile.memory_source is None


async def test_profile_survives_service_recreation_through_database(tmp_path) -> None:
    """A profile persisted in SQLite is recoverable by a fresh service instance."""
    database = make_database(tmp_path)
    try:
        service = ProfileService(
            DatabaseUserBehaviorRepository(database),
            MockLLMProvider(),
            profile_repository=DatabaseUserProfileRepository(database),
            memory_store=InMemoryMemoryStore(),
        )
        built = await service.get_or_build_profile("u-demo-001")
        assert built.profile_persisted is True

        fresh_repository = DatabaseUserProfileRepository(database)
        stored = fresh_repository.get_profile("u-demo-001")
        assert stored is not None
        assert stored.profile.user_id == built.user_id
        assert stored.profile.data_source is DataSource.DATABASE
    finally:
        database.dispose()


async def test_invalidate_removes_cache_and_persisted_profile() -> None:
    """Invalidation is explicit and removes both layers."""
    service, _memory, profile_repository = _service_with_memory()
    await service.get_or_build_profile("u-demo-001")

    await service.invalidate_profile_cache("u-demo-001")

    assert profile_repository.get_profile("u-demo-001") is None


class BrokenRedisMemory:
    """Redis-shaped store that fails every operation."""

    source = DataSource.REDIS

    async def record_behavior(self, event: BehaviorEvent) -> None:
        raise ConnectionError("redis down")

    async def get_recent_behaviors(
        self,
        user_id: str,
        *,
        behavior_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[BehaviorEvent]:
        raise ConnectionError("redis down")

    async def cache_profile(self, profile, *, ttl_seconds: int) -> None:
        raise ConnectionError("redis down")

    async def get_cached_profile(self, user_id: str):
        raise ConnectionError("redis down")

    async def invalidate_profile_cache(self, user_id: str) -> None:
        raise ConnectionError("redis down")

    async def set_session_context(
        self, session_id: str, context: dict[str, Any], *, ttl_seconds: int
    ) -> None:
        raise ConnectionError("redis down")

    async def get_session_context(self, session_id: str) -> dict[str, Any] | None:
        raise ConnectionError("redis down")

    async def close(self) -> None:
        return None


async def test_redis_failure_degrades_profile_to_database() -> None:
    """A broken Redis connection yields warnings and still builds a DB profile."""
    service = ProfileService(
        InMemoryUserBehaviorRepository(),
        MockLLMProvider(),
        profile_repository=InMemoryUserProfileRepository(),
        memory_store=BrokenRedisMemory(),  # type: ignore[arg-type]
    )

    profile = await service.get_or_build_profile("u-demo-001")

    assert profile.profile_persisted is True
    assert profile.data_source is DataSource.IN_MEMORY_DEMO
    assert "memory_read_failed" in profile.warnings
    assert "profile_cache_write_failed" in profile.warnings
