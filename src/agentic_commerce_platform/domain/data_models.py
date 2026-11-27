"""Domain contracts for persistent behavior, profiles, and retrieval."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator

from agentic_commerce_platform.domain.agent_models import UserProfileOutput
from agentic_commerce_platform.domain.enums import BehaviorType, RetrievalSource
from agentic_commerce_platform.domain.models import PlatformModel, Product

__all__ = [
    "BehaviorEvent",
    "PersistedUserProfile",
    "RetrievalResult",
    "RetrievedCandidate",
    "VectorHit",
    "VectorRecord",
]


class BehaviorEvent(PlatformModel):
    """One append-only user behavior event."""

    user_id: str = Field(min_length=1, max_length=128)
    behavior_type: BehaviorType
    item_id: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=100)
    amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=12,
        decimal_places=2,
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, value: str) -> str:
        """Reject blank user IDs."""
        if not value.strip():
            raise ValueError("user_id must not be blank")
        return value


class PersistedUserProfile(PlatformModel):
    """A stored profile snapshot with its persistence timestamp."""

    profile: UserProfileOutput
    updated_at: datetime


class RetrievedCandidate(PlatformModel):
    """A product candidate returned by semantic or keyword retrieval."""

    product: Product
    score: float = Field(ge=0.0, le=1.0)
    source: RetrievalSource
    retrieval_query: str
    matched_fields: list[str] = Field(default_factory=list)
    embedding_model: str | None = Field(default=None, max_length=100)


class RetrievalResult(PlatformModel):
    """Aggregated retrieval result with provenance and degraded-mode warnings."""

    query: str
    candidates: list[RetrievedCandidate] = Field(default_factory=list)
    retrieval_source: str
    warnings: list[str] = Field(default_factory=list)
    embedding_model: str | None = Field(default=None, max_length=100)


class VectorRecord(PlatformModel):
    """A product embedding stored in a local or external vector store."""

    product_id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=4000)
    vector: list[float] = Field(min_length=1)
    embedding_model: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class VectorHit(PlatformModel):
    """One raw similarity result from a vector store."""

    product_id: str
    score: float = Field(ge=0.0, le=1.0)
    embedding_model: str | None = None

