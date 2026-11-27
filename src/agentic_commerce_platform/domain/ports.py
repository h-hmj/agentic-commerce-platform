"""Ports implemented by phase-two through phase-four data adapters."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from agentic_commerce_platform.domain.agent_models import (
    UserBehaviorRecord,
    UserProfileOutput,
)
from agentic_commerce_platform.domain.data_models import (
    BehaviorEvent,
    PersistedUserProfile,
    RetrievalResult,
    VectorHit,
    VectorRecord,
)
from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.domain.models import Product

__all__ = [
    "CatalogRepository",
    "EmbeddingProvider",
    "InventoryRepository",
    "MemoryStore",
    "RetrievalPort",
    "UserBehaviorRepository",
    "UserProfileRepository",
    "UserRepository",
    "VectorStore",
]


@runtime_checkable
class CatalogRepository(Protocol):
    """Product catalog contract used by catalog and retrieval services."""

    @property
    def source(self) -> DataSource:
        """Explicit provenance of returned products."""
        ...

    def search(
        self,
        *,
        query: str = "",
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        limit: int | None = None,
        active_only: bool = True,
    ) -> list[Product]:
        """Return products matching all supplied filters."""
        ...

    def get_by_ids(self, product_ids: list[str]) -> list[Product]:
        """Return products by ID in input-independent stable order."""
        ...


@runtime_checkable
class InventoryRepository(Protocol):
    """Stock lookup and controlled update contract."""

    @property
    def source(self) -> DataSource:
        """Explicit provenance of stock values."""
        ...

    def get_stock(self, product_id: str) -> int | None:
        """Return current stock, or ``None`` when no inventory record exists."""
        ...

    def get_stock_levels(self, product_ids: list[str]) -> dict[str, int | None]:
        """Return stock for multiple product IDs without assuming missing stock."""
        ...

    def update_stock(self, product_id: str, stock: int) -> int:
        """Set non-negative stock and return the new value."""
        ...


@runtime_checkable
class UserBehaviorRepository(Protocol):
    """Historical behavior contract used by profile and memory flows."""

    @property
    def source(self) -> DataSource:
        """Explicit provenance of behavior records."""
        ...

    def get_behavior(self, user_id: str) -> UserBehaviorRecord | None:
        """Return an aggregated behavior record for profile rules."""
        ...

    def get_recent_behaviors(
        self,
        user_id: str,
        *,
        behavior_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[BehaviorEvent]:
        """Return recent append-only behavior events, newest first."""
        ...

    def record_behavior(self, event: BehaviorEvent) -> BehaviorEvent:
        """Persist one behavior event and return it."""
        ...


@runtime_checkable
class UserProfileRepository(Protocol):
    """Long-term persisted user profile contract."""

    @property
    def source(self) -> DataSource:
        """Provenance of persisted profiles."""
        ...

    def get_profile(self, user_id: str) -> PersistedUserProfile | None:
        """Return a stored profile or ``None``."""
        ...

    def save_profile(self, profile: UserProfileOutput) -> PersistedUserProfile:
        """Insert or update a profile and return the stored snapshot."""
        ...

    def invalidate(self, user_id: str) -> bool:
        """Delete a stored profile; return whether one was removed."""
        ...


@runtime_checkable
class UserRepository(Protocol):
    """Minimal user identity contract."""

    @property
    def source(self) -> DataSource:
        """Provenance of user records."""
        ...

    def ensure_user(self, user_id: str) -> None:
        """Create a user record if it does not exist."""
        ...

    def exists(self, user_id: str) -> bool:
        """Return whether a user exists."""
        ...


@runtime_checkable
class MemoryStore(Protocol):
    """Short-term behavior, session, and profile-cache contract."""

    @property
    def source(self) -> DataSource:
        """Current memory backend provenance."""
        ...

    async def record_behavior(self, event: BehaviorEvent) -> None:
        """Append a behavior event to short-term memory."""
        ...

    async def get_recent_behaviors(
        self,
        user_id: str,
        *,
        behavior_type: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> list[BehaviorEvent]:
        """Read recent behavior events from short-term memory."""
        ...

    async def cache_profile(
        self,
        profile: UserProfileOutput,
        *,
        ttl_seconds: int,
    ) -> None:
        """Cache a user profile with a finite TTL."""
        ...

    async def get_cached_profile(self, user_id: str) -> UserProfileOutput | None:
        """Return a cached profile if it has not expired."""
        ...

    async def invalidate_profile_cache(self, user_id: str) -> None:
        """Remove one cached profile."""
        ...

    async def set_session_context(
        self,
        session_id: str,
        context: dict[str, Any],
        *,
        ttl_seconds: int,
    ) -> None:
        """Store bounded short-term session context."""
        ...

    async def get_session_context(self, session_id: str) -> dict[str, Any] | None:
        """Return unexpired session context."""
        ...

    async def close(self) -> None:
        """Release backend resources."""
        ...


@runtime_checkable
class RetrievalPort(Protocol):
    """Retrieval contract consumed by CatalogAgent without importing services."""

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        top_k: int | None = None,
        include_out_of_stock: bool = False,
    ) -> RetrievalResult:
        """Return retrieval candidates with provenance and scores."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Provider-agnostic embedding contract."""

    @property
    def model_name(self) -> str:
        """Stable embedding model identifier."""
        ...

    def embed_text(self, text: str) -> list[float]:
        """Embed one non-empty text."""
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of non-empty texts in order."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Local or external vector-store contract."""

    def upsert(self, record: VectorRecord) -> None:
        """Insert or replace one product vector."""
        ...

    def search(
        self,
        vector: list[float],
        *,
        top_k: int,
        score_threshold: float,
    ) -> list[VectorHit]:
        """Return similarity hits ordered by descending score."""
        ...

    def delete(self, product_id: str) -> None:
        """Delete a product vector."""
        ...

    def count(self) -> int:
        """Return the number of stored vectors."""
        ...
