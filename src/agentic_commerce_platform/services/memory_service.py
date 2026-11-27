"""Short-term memory and durable behavior recording service."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from agentic_commerce_platform.domain.data_models import BehaviorEvent
from agentic_commerce_platform.domain.errors import ExternalServiceError
from agentic_commerce_platform.domain.ports import MemoryStore, UserBehaviorRepository

__all__ = ["MemoryService"]

logger = logging.getLogger(__name__)


class MemoryService:
    """Record behavior in memory and durable history, with explicit degradation."""

    def __init__(
        self,
        memory_store: MemoryStore,
        behavior_repository: UserBehaviorRepository,
    ) -> None:
        """Inject memory and historical behavior ports."""
        self._memory_store = memory_store
        self._behavior_repository = behavior_repository

    @property
    def memory_source(self) -> str:
        """Expose the active memory backend marker."""
        return self._memory_store.source.value

    async def record_behavior(self, event: BehaviorEvent) -> BehaviorEvent:
        """Persist history first, then append short-term memory.

        A memory failure is logged and raised as a structured external error; it
        is never reported as a successful Redis write.
        """
        stored = self._behavior_repository.record_behavior(event)
        try:
            await self._memory_store.record_behavior(stored)
            await self._memory_store.invalidate_profile_cache(stored.user_id)
        except Exception as exc:
            logger.warning("memory_behavior_write_failed", exc_info=True)
            raise ExternalServiceError(
                "Short-term memory write failed; durable history was stored.",
                service_name="memory_store",
            ) from exc
        return stored

    async def recent_behaviors(
        self,
        user_id: str,
        *,
        behavior_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[BehaviorEvent]:
        """Read recent memory behaviors, falling back to durable history."""
        try:
            events = await self._memory_store.get_recent_behaviors(
                user_id,
                behavior_type=behavior_type,
                since=since,
                limit=limit,
            )
        except Exception:
            logger.warning("memory_read_failed_falling_back_to_database", exc_info=True)
            return self._behavior_repository.get_recent_behaviors(
                user_id,
                behavior_type=behavior_type,
                since=since,
                limit=limit,
            )
        return events

    async def set_session_context(
        self,
        session_id: str,
        context: dict[str, Any],
        *,
        ttl_seconds: int,
    ) -> None:
        """Store session context through the configured memory backend."""
        await self._memory_store.set_session_context(
            session_id,
            context,
            ttl_seconds=ttl_seconds,
        )

    async def get_session_context(self, session_id: str) -> dict[str, Any] | None:
        """Read session context through the configured memory backend."""
        return await self._memory_store.get_session_context(session_id)
