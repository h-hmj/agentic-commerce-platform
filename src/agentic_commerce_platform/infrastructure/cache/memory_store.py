"""In-process short-term memory store used when Redis is disabled/unavailable."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from agentic_commerce_platform.domain.agent_models import UserProfileOutput
from agentic_commerce_platform.domain.data_models import BehaviorEvent
from agentic_commerce_platform.domain.enums import DataSource

__all__ = ["InMemoryMemoryStore"]


class InMemoryMemoryStore:
    """Bounded, TTL-aware in-process memory store.

    It is intentionally process-local. Restarting the process loses these
    short-term behaviors, sessions, and cached profiles; durable history belongs
    in the database.
    """

    def __init__(self) -> None:
        """Create empty behavior, profile, and session stores."""
        self._behaviors: dict[str, list[BehaviorEvent]] = {}
        self._profiles: dict[str, tuple[UserProfileOutput, float]] = {}
        self._sessions: dict[str, tuple[dict[str, Any], float]] = {}

    @property
    def source(self) -> DataSource:
        """Return in-process memory provenance."""
        return DataSource.IN_MEMORY

    async def record_behavior(self, event: BehaviorEvent) -> None:
        """Append a behavior and retain at most 200 recent events per user."""
        events = self._behaviors.setdefault(event.user_id, [])
        events.append(event.model_copy(deep=True))
        events.sort(key=lambda item: item.occurred_at, reverse=True)
        del events[200:]

    async def get_recent_behaviors(
        self,
        user_id: str,
        *,
        behavior_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[BehaviorEvent]:
        """Return recent events, optionally filtered by type and time."""
        events = [
            event
            for event in self._behaviors.get(user_id, [])
            if (behavior_type is None or event.behavior_type.value == behavior_type)
            and (since is None or event.occurred_at >= since)
        ]
        events.sort(key=lambda event: event.occurred_at, reverse=True)
        return [event.model_copy(deep=True) for event in events[:limit]]

    async def cache_profile(
        self,
        profile: UserProfileOutput,
        *,
        ttl_seconds: int,
    ) -> None:
        """Cache a profile until a monotonic deadline."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._profiles[profile.user_id] = (
            profile.model_copy(deep=True),
            time.monotonic() + ttl_seconds,
        )

    async def get_cached_profile(self, user_id: str) -> UserProfileOutput | None:
        """Return an unexpired cached profile."""
        entry = self._profiles.get(user_id)
        if entry is None:
            return None
        profile, expires_at = entry
        if time.monotonic() >= expires_at:
            self._profiles.pop(user_id, None)
            return None
        return profile.model_copy(deep=True)

    async def invalidate_profile_cache(self, user_id: str) -> None:
        """Remove a cached profile."""
        self._profiles.pop(user_id, None)

    async def set_session_context(
        self,
        session_id: str,
        context: dict[str, Any],
        *,
        ttl_seconds: int,
    ) -> None:
        """Store a bounded short-term session context."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._sessions[session_id] = (
            dict(context),
            time.monotonic() + ttl_seconds,
        )

    async def get_session_context(self, session_id: str) -> dict[str, Any] | None:
        """Return an unexpired session context."""
        entry = self._sessions.get(session_id)
        if entry is None:
            return None
        context, expires_at = entry
        if time.monotonic() >= expires_at:
            self._sessions.pop(session_id, None)
            return None
        return dict(context)

    async def close(self) -> None:
        """Release in-memory data (no external resources)."""
        self._behaviors.clear()
        self._profiles.clear()
        self._sessions.clear()
