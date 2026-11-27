"""Profile use cases spanning real-time memory, history, and persistence."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from agentic_commerce_platform.agents.profile_agent import UserProfileAgent
from agentic_commerce_platform.domain.agent_models import UserProfileInput, UserProfileOutput
from agentic_commerce_platform.domain.data_models import BehaviorEvent
from agentic_commerce_platform.domain.enums import BehaviorType
from agentic_commerce_platform.domain.errors import ConfigurationError
from agentic_commerce_platform.domain.ports import (
    MemoryStore,
    UserBehaviorRepository,
    UserProfileRepository,
)
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider
from agentic_commerce_platform.services.agent_runner import run_agent_for_output

__all__ = ["ProfileService"]

logger = logging.getLogger(__name__)


class ProfileService:
    """Build profiles from the documented data-source priority.

    Priority is explicit request behavior, short-term memory, historical
    behavior, persisted profile, then default profile. The UserProfileAgent owns
    rule derivation; this service exposes profile/memory use cases without
    moving profile rules into the API layer.
    """

    def __init__(
        self,
        behavior_repository: UserBehaviorRepository,
        llm_provider: LLMProvider,
        *,
        profile_repository: UserProfileRepository | None = None,
        memory_store: MemoryStore | None = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        """Create the service and inject all optional persistence dependencies."""
        self._behavior_repository = behavior_repository
        self._profile_repository = profile_repository
        self._memory_store = memory_store
        self._cache_ttl_seconds = cache_ttl_seconds
        self._agent = UserProfileAgent(
            behavior_repository,
            llm_provider,
            profile_repository=profile_repository,
            memory_store=memory_store,
            cache_ttl_seconds=cache_ttl_seconds,
        )

    @property
    def agent(self) -> UserProfileAgent:
        """Return the service-owned agent for introspection in tests."""
        return self._agent

    @property
    def profile_repository(self) -> UserProfileRepository | None:
        """Return the optional long-term profile repository."""
        return self._profile_repository

    async def build_profile(self, request: UserProfileInput) -> UserProfileOutput:
        """Build a profile from an already assembled request."""
        return await run_agent_for_output(self._agent, request, UserProfileOutput)

    async def get_or_build_profile(
        self,
        user_id: str,
        *,
        explicit_input: UserProfileInput | None = None,
    ) -> UserProfileOutput:
        """Return/build a profile using the agent's explicit source priority."""
        request = explicit_input or UserProfileInput(user_id=user_id)
        if request.user_id != user_id:
            raise ValueError("explicit input user_id does not match requested user")
        return await self.build_profile(request)

    async def build_profile_from_behaviors(
        self,
        user_id: str,
        events: list[BehaviorEvent],
    ) -> UserProfileOutput:
        """Summarize behavior events into an input and run the profile agent."""
        request = UserProfileInput(
            user_id=user_id,
            recent_views=[
                event.item_id
                for event in events
                if event.item_id and event.behavior_type is BehaviorType.VIEW
            ],
            recent_clicks=[
                event.item_id
                for event in events
                if event.item_id and event.behavior_type is BehaviorType.CLICK
            ],
            recent_purchases=[
                event.item_id
                for event in events
                if event.item_id and event.behavior_type is BehaviorType.PURCHASE
            ],
            category_counts=self._category_counts(events),
            average_order_value=self._average_order_value(events),
            days_since_last_active=self._days_since_active(events),
        )
        return await self.build_profile(request)

    async def save_profile(self, profile: UserProfileOutput) -> UserProfileOutput:
        """Persist a profile and update the memory cache when configured."""
        if self._profile_repository is None:
            raise ConfigurationError("Profile persistence is not configured.")
        saved = self._profile_repository.save_profile(profile)
        if self._memory_store is not None:
            try:
                await self._memory_store.cache_profile(
                    saved.profile.model_copy(update={"profile_persisted": True}),
                    ttl_seconds=self._cache_ttl_seconds,
                )
            except Exception:
                logger.warning("profile_cache_write_failed", exc_info=True)
        return saved.profile.model_copy(update={"profile_persisted": True})

    async def invalidate_profile_cache(self, user_id: str) -> None:
        """Invalidate both short-term cache and persistent profile when present."""
        if self._memory_store is not None:
            await self._memory_store.invalidate_profile_cache(user_id)
        if self._profile_repository is not None:
            self._profile_repository.invalidate(user_id)

    async def record_behavior_and_refresh_profile(
        self,
        event: BehaviorEvent,
    ) -> UserProfileOutput:
        """Write behavior to history/memory, invalidate cache, and rebuild profile."""
        stored = self._behavior_repository.record_behavior(event)
        if self._memory_store is not None:
            try:
                await self._memory_store.record_behavior(stored)
            except Exception:
                logger.warning("profile_memory_behavior_write_failed", exc_info=True)
            try:
                await self._memory_store.invalidate_profile_cache(stored.user_id)
            except Exception:
                logger.warning("profile_memory_cache_invalidate_failed", exc_info=True)
        return await self.get_or_build_profile(stored.user_id)

    @staticmethod
    def _category_counts(events: list[BehaviorEvent]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in events:
            if event.category:
                counts[event.category] = counts.get(event.category, 0) + 1
        return counts

    @staticmethod
    def _average_order_value(events: list[BehaviorEvent]) -> Decimal | None:
        amounts = [
            event.amount
            for event in events
            if event.behavior_type is BehaviorType.PURCHASE and event.amount is not None
        ]
        return sum(amounts, Decimal("0")) / len(amounts) if amounts else None

    @staticmethod
    def _days_since_active(events: list[BehaviorEvent]) -> int | None:
        if not events:
            return None
        latest = max(event.occurred_at for event in events)
        return max(0, (datetime.now(UTC) - latest).days)
