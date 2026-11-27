"""Optional Redis-backed short-term memory adapter.

The Redis package and server are optional for tests. This module imports Redis
only inside the factory; the InMemoryMemoryStore is always available offline.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from agentic_commerce_platform.domain.agent_models import UserProfileOutput
from agentic_commerce_platform.domain.data_models import BehaviorEvent
from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.domain.errors import ExternalServiceError
from agentic_commerce_platform.settings import Settings

__all__ = ["RedisMemoryStore", "create_redis_memory_store"]


class RedisMemoryStore:
    """Redis short-term behavior/session/profile cache adapter.

    The injected client is duck-typed as ``redis.asyncio.Redis``. Every key is
    namespaced by a configurable prefix, and all writes have finite TTLs.
    """

    def __init__(
        self,
        client: Any,
        *,
        key_prefix: str,
        behavior_ttl_seconds: int = 86400,
        profile_ttl_seconds: int = 300,
        session_ttl_seconds: int = 1800,
    ) -> None:
        """Store an injected Redis client and TTL policy."""
        if not key_prefix.strip():
            raise ValueError("key_prefix must not be blank")
        for value in (behavior_ttl_seconds, profile_ttl_seconds, session_ttl_seconds):
            if value <= 0:
                raise ValueError("Redis TTL values must be positive")
        self._client = client
        self._prefix = key_prefix.strip()
        self._behavior_ttl = behavior_ttl_seconds
        self._profile_ttl = profile_ttl_seconds
        self._session_ttl = session_ttl_seconds

    @property
    def source(self) -> DataSource:
        """Return Redis provenance."""
        return DataSource.REDIS

    def _key(self, *parts: str) -> str:
        return ":".join((self._prefix, *parts))

    async def record_behavior(self, event: BehaviorEvent) -> None:
        """Append a JSON behavior event to all/type lists with TTL."""
        payload = event.model_dump_json()
        keys = (
            self._key("behavior", event.user_id, "all"),
            self._key("behavior", event.user_id, event.behavior_type.value),
        )
        try:
            for key in keys:
                await self._client.lpush(key, payload)
                await self._client.ltrim(key, 0, 199)
                await self._client.expire(key, self._behavior_ttl)
        except Exception as exc:
            raise ExternalServiceError(
                f"Redis behavior write failed: {exc}",
                service_name="redis",
            ) from exc

    async def get_recent_behaviors(
        self,
        user_id: str,
        *,
        behavior_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[BehaviorEvent]:
        """Read recent behavior JSON entries from Redis."""
        suffix = behavior_type or "all"
        key = self._key("behavior", user_id, suffix)
        try:
            raw_values = await self._client.lrange(key, 0, max(limit * 2, 99))
        except Exception as exc:
            raise ExternalServiceError(
                f"Redis behavior read failed: {exc}",
                service_name="redis",
            ) from exc

        events: list[BehaviorEvent] = []
        for raw in raw_values:
            try:
                event = BehaviorEvent.model_validate_json(raw)
            except Exception:
                continue
            if since is not None and event.occurred_at < since:
                continue
            events.append(event)
            if len(events) >= limit:
                break
        return events

    async def cache_profile(
        self,
        profile: UserProfileOutput,
        *,
        ttl_seconds: int,
    ) -> None:
        """Cache a serialized profile with finite TTL."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        try:
            await self._client.set(
                self._key("profile", profile.user_id),
                profile.model_dump_json(),
                ex=ttl_seconds,
            )
        except Exception as exc:
            raise ExternalServiceError(
                f"Redis profile cache write failed: {exc}",
                service_name="redis",
            ) from exc

    async def get_cached_profile(self, user_id: str) -> UserProfileOutput | None:
        """Read and validate a cached profile."""
        try:
            raw = await self._client.get(self._key("profile", user_id))
        except Exception as exc:
            raise ExternalServiceError(
                f"Redis profile cache read failed: {exc}",
                service_name="redis",
            ) from exc
        return UserProfileOutput.model_validate_json(raw) if raw else None

    async def invalidate_profile_cache(self, user_id: str) -> None:
        """Delete one cached profile."""
        try:
            await self._client.delete(self._key("profile", user_id))
        except Exception as exc:
            raise ExternalServiceError(
                f"Redis profile cache invalidation failed: {exc}",
                service_name="redis",
            ) from exc

    async def set_session_context(
        self,
        session_id: str,
        context: dict[str, Any],
        *,
        ttl_seconds: int,
    ) -> None:
        """Store JSON session context with TTL."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        try:
            await self._client.set(
                self._key("session", session_id),
                json.dumps(context, default=str),
                ex=ttl_seconds,
            )
        except Exception as exc:
            raise ExternalServiceError(
                f"Redis session write failed: {exc}",
                service_name="redis",
            ) from exc

    async def get_session_context(self, session_id: str) -> dict[str, Any] | None:
        """Read JSON session context."""
        try:
            raw = await self._client.get(self._key("session", session_id))
        except Exception as exc:
            raise ExternalServiceError(
                f"Redis session read failed: {exc}",
                service_name="redis",
            ) from exc
        return json.loads(raw) if raw else None

    async def close(self) -> None:
        """Close the underlying Redis client."""
        close = getattr(self._client, "aclose", None) or getattr(
            self._client, "close", None
        )
        if close is not None:
            try:
                result = close()
                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:
                raise ExternalServiceError(
                    f"Redis close failed: {exc}",
                    service_name="redis",
                ) from exc


async def create_redis_memory_store(
    settings: Settings,
    *,
    client: Any | None = None,
) -> RedisMemoryStore:
    """Create and ping a Redis adapter, or use an injected test client."""
    if client is None:
        try:
            import redis.asyncio as redis
        except ImportError as exc:
            raise ExternalServiceError(
                "Redis package is not installed; install the redis dependency.",
                service_name="redis",
            ) from exc
        client = redis.from_url(
            settings.redis_url.get_secret_value(),
            decode_responses=True,
        )
        try:
            await client.ping()
        except Exception as exc:
            raise ExternalServiceError(
                f"Redis is enabled but unavailable: {exc}",
                service_name="redis",
            ) from exc
    return RedisMemoryStore(
        client,
        key_prefix=settings.redis_key_prefix,
        profile_ttl_seconds=settings.profile_cache_ttl_seconds,
        session_ttl_seconds=settings.session_context_ttl_seconds,
    )
