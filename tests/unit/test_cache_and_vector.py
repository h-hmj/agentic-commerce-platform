"""Memory-store, embedding, and vector-store tests without external services."""

from __future__ import annotations

import sys

import pytest

from agentic_commerce_platform.api.composition import _build_memory_store
from agentic_commerce_platform.domain.data_models import BehaviorEvent, VectorRecord
from agentic_commerce_platform.domain.enums import BehaviorType, DataSource
from agentic_commerce_platform.domain.errors import ExternalServiceError
from agentic_commerce_platform.infrastructure.cache.memory_store import InMemoryMemoryStore
from agentic_commerce_platform.infrastructure.cache.redis_client import RedisMemoryStore
from agentic_commerce_platform.infrastructure.vector_store import (
    DeterministicEmbeddingProvider,
    InMemoryVectorStore,
    SQLiteVectorStore,
)
from tests.helpers import make_profile
from tests.phase4_helpers import make_database, make_real_settings


class FakeRedisClient:
    """Async in-memory subset of redis client commands used by the adapter."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.closed = False

    async def lpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).insert(0, value)

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        self.lists[key] = self.lists.get(key, [])[start : stop + 1]

    async def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        return self.lists.get(key, [])[start : stop + 1]

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.lists.pop(key, None)

    async def aclose(self) -> None:
        self.closed = True


def _behavior(user_id: str = "u-1") -> BehaviorEvent:
    return BehaviorEvent(
        user_id=user_id,
        behavior_type=BehaviorType.VIEW,
        item_id="p-001",
        category="books",
    )


async def test_in_memory_store_behaviors_cache_sessions_and_ttl(monkeypatch) -> None:
    """InMemory store supports behavior, profile cache, session TTL, and close."""
    store = InMemoryMemoryStore()
    clock = [1000.0]
    monkeypatch.setattr(
        "agentic_commerce_platform.infrastructure.cache.memory_store.time.monotonic",
        lambda: clock[0],
    )
    await store.record_behavior(_behavior())
    assert len(await store.get_recent_behaviors("u-1")) == 1
    assert store.source is DataSource.IN_MEMORY

    profile = make_profile()
    await store.cache_profile(profile, ttl_seconds=10)
    assert (await store.get_cached_profile(profile.user_id)) is not None
    clock[0] += 11
    assert await store.get_cached_profile(profile.user_id) is None

    await store.set_session_context("session-1", {"step": 1}, ttl_seconds=10)
    assert await store.get_session_context("session-1") == {"step": 1}
    clock[0] += 11
    assert await store.get_session_context("session-1") is None

    await store.close()
    assert await store.get_recent_behaviors("u-1") == []


async def test_redis_store_uses_prefix_ttls_and_forwards_operations() -> None:
    """Redis adapter namespaces keys, applies TTLs, and round-trips JSON."""
    client = FakeRedisClient()
    store = RedisMemoryStore(client, key_prefix="test-prefix")

    event = _behavior()
    await store.record_behavior(event)
    assert any(key.startswith("test-prefix:behavior:u-1") for key in client.lists)
    assert all(value > 0 for value in client.expirations.values())
    assert len(await store.get_recent_behaviors("u-1")) == 1

    profile = make_profile()
    await store.cache_profile(profile, ttl_seconds=30)
    assert await store.get_cached_profile(profile.user_id) is not None
    await store.set_session_context("s-1", {"step": 2}, ttl_seconds=30)
    assert await store.get_session_context("s-1") == {"step": 2}

    await store.invalidate_profile_cache(profile.user_id)
    assert await store.get_cached_profile(profile.user_id) is None
    await store.close()
    assert client.closed is True


async def test_redis_store_raises_structured_failure() -> None:
    """Redis errors are not silently converted into successful writes."""
    class BrokenClient(FakeRedisClient):
        async def lpush(self, key: str, value: str) -> None:
            raise ConnectionError("redis down")

    store = RedisMemoryStore(BrokenClient(), key_prefix="test")

    with pytest.raises(ExternalServiceError) as exc_info:
        await store.record_behavior(_behavior())

    assert exc_info.value.service_name == "redis"


def test_missing_redis_package_falls_back_to_in_memory(tmp_path, monkeypatch) -> None:
    """redis_enabled=true without an installed package degrades explicitly."""
    settings = make_real_settings(
        tmp_path,
        use_real_adapters=False,
        redis_enabled=True,
    )
    monkeypatch.setitem(sys.modules, "redis", None)

    store = _build_memory_store(settings)

    assert isinstance(store, InMemoryMemoryStore)


def test_deterministic_embeddings_are_stable_and_batchable() -> None:
    """The local embedding provider is reproducible and rejects blank text."""
    provider = DeterministicEmbeddingProvider(dimensions=32)
    first = provider.embed_text("Python 编程")
    second = provider.embed_text("Python 编程")
    batch = provider.embed_documents(["Python 编程", "咖啡"])

    assert first == second
    assert len(first) == 32
    assert len(batch) == 2
    assert provider.model_name == "deterministic-hash-v1"
    with pytest.raises(ValueError):
        provider.embed_text("   ")


async def test_in_memory_vector_store_search_and_threshold() -> None:
    """Vector search applies top-k, threshold, delete, and count."""
    store = InMemoryVectorStore()
    vector = [1.0, 0.0]
    store.upsert(
        VectorRecord(
            product_id="p-1",
            text="Python",
            vector=vector,
            embedding_model="test",
        )
    )
    store.upsert(
        VectorRecord(
            product_id="p-2",
            text="Coffee",
            vector=[0.0, 1.0],
            embedding_model="test",
        )
    )

    assert store.count() == 2
    hits = store.search([1.0, 0.0], top_k=2, score_threshold=0.5)
    assert [hit.product_id for hit in hits] == ["p-1"]
    store.delete("p-1")
    assert store.count() == 1


async def test_sqlite_vector_store_persists_vectors(tmp_path) -> None:
    """The local SQLite vector store spans separate instances of the adapter."""
    database = make_database(tmp_path)
    try:
        store = SQLiteVectorStore(database, collection="test")
        store.upsert(
            VectorRecord(
                product_id="p-001",
                text="Python",
                vector=[1.0, 0.0],
                embedding_model="test",
            )
        )
        fresh = SQLiteVectorStore(database, collection="test")
        assert fresh.count() == 1
        assert fresh.search([1.0, 0.0], top_k=1, score_threshold=0.5)[0].product_id == "p-001"
        fresh.delete("p-001")
        assert fresh.count() == 0
    finally:
        database.dispose()
