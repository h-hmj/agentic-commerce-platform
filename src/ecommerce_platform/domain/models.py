"""Pydantic domain models shared by the API, services, and future agents."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ecommerce_platform.domain.enums import RecommendationScene, RecommendationStatus

__all__ = [
    "AgentResult",
    "ErrorDetail",
    "ErrorResponse",
    "Product",
    "RecommendationContext",
    "RecommendationRequest",
    "RecommendationResponse",
]


class PlatformModel(BaseModel):
    """Common configuration for strict, validated value models."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class RecommendationContext(PlatformModel):
    """Structured, non-sensitive context supplied with a recommendation request.

    Free-form dictionaries deliberately do not appear on the public request
    surface. New context fields should be added explicitly so they can be
    reviewed, validated, and excluded from logs where appropriate.
    """

    device_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=32,
        description="Client device type, for example mobile or desktop.",
    )
    locale: str = Field(
        default="zh-CN",
        min_length=2,
        max_length=16,
        description="Requested content locale.",
    )
    category: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Optional category context for the scene.",
    )
    keywords: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Optional search keywords; never logged in full.",
    )

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: list[str]) -> list[str]:
        """Reject blank or oversized keywords and normalize whitespace."""
        cleaned: list[str] = []
        for keyword in value:
            stripped = keyword.strip()
            if not stripped:
                raise ValueError("keywords must not contain blank values")
            if len(stripped) > 64:
                raise ValueError("each keyword must be at most 64 characters")
            cleaned.append(stripped)
        return cleaned


class RecommendationRequest(PlatformModel):
    """Input contract for a recommendation request."""

    user_id: str = Field(
        min_length=1,
        max_length=128,
        description="Stable, non-empty user identifier.",
    )
    scene: RecommendationScene = Field(
        default=RecommendationScene.HOME,
        description="Storefront scene that triggered the request.",
    )
    num_items: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of items requested, bounded to a safe range.",
    )
    context: RecommendationContext = Field(
        default_factory=RecommendationContext,
        description="Structured request context.",
    )

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, value: str) -> str:
        """Reject identifiers containing only whitespace."""
        if not value.strip():
            raise ValueError("user_id must not be blank")
        return value


class Product(PlatformModel):
    """Product summary used by the future retrieval and recommendation flows."""

    product_id: str = Field(
        min_length=1,
        max_length=64,
        description="Stable product identifier.",
    )
    name: str = Field(
        min_length=1,
        max_length=200,
        description="Human-readable product name.",
    )
    category: str = Field(
        min_length=1,
        max_length=100,
        description="Product category.",
    )
    price: Decimal = Field(
        ge=Decimal("0"),
        max_digits=12,
        decimal_places=2,
        description="Non-negative price with up to two decimal places.",
    )
    stock: int = Field(
        ge=0,
        description="Non-negative available stock.",
    )
    tags: list[str] = Field(
        default_factory=list,
        max_length=30,
        description="Search and recommendation tags.",
    )

    @field_validator("product_id", "name", "category")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        """Reject required string fields that contain only whitespace."""
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        """Reject blank or oversized product tags and normalize whitespace."""
        cleaned: list[str] = []
        for tag in value:
            stripped = tag.strip()
            if not stripped:
                raise ValueError("tags must not contain blank values")
            if len(stripped) > 64:
                raise ValueError("each tag must be at most 64 characters")
            cleaned.append(stripped)
        return cleaned


class AgentResult(PlatformModel):
    """Uniform structured result returned by every agent invocation."""

    agent_name: str = Field(
        min_length=1,
        max_length=100,
        description="Name of the agent that produced this result.",
    )
    success: bool = Field(description="Whether the agent completed successfully.")
    latency_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Measured wall-clock execution time in milliseconds.",
    )
    error: str | None = Field(
        default=None,
        max_length=1000,
        description="Sanitized failure description; present only on failure.",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional calibrated confidence in the result.",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Agent-specific structured output.",
    )

    @model_validator(mode="after")
    def validate_success_error_consistency(self) -> AgentResult:
        """Require failures to carry a reason and successes to remain clean."""
        if not self.success and not self.error:
            raise ValueError("a failed AgentResult must include a non-empty error")
        if self.success and self.error is not None:
            raise ValueError("a successful AgentResult must not include an error")
        return self


class RecommendationResponse(PlatformModel):
    """Response contract for the recommendation endpoint."""

    request_id: str = Field(
        min_length=1,
        max_length=128,
        description="Correlation identifier for this request.",
    )
    user_id: str = Field(
        min_length=1,
        max_length=128,
        description="User identifier echoed from the request.",
    )
    status: RecommendationStatus = Field(
        description="Lifecycle status of the recommendation result.",
    )
    products: list[Product] = Field(
        default_factory=list,
        description="Recommended products. Empty in the phase-one skeleton.",
    )
    messages: list[str] = Field(
        default_factory=list,
        description="Human-readable status or explanatory messages.",
    )
    agent_results: dict[str, AgentResult] = Field(
        default_factory=dict,
        description="Results keyed by agent name.",
    )
    total_latency_ms: float = Field(
        ge=0.0,
        description="End-to-end service execution time in milliseconds.",
    )


class ErrorDetail(PlatformModel):
    """Stable machine-readable error payload."""

    code: str = Field(
        min_length=1,
        max_length=64,
        description="Stable error code suitable for client branching.",
    )
    message: str = Field(
        min_length=1,
        max_length=500,
        description="Safe, user-facing error message.",
    )
    details: dict[str, Any] | None = Field(
        default=None,
        description="Optional safe validation or context details.",
    )


class ErrorResponse(PlatformModel):
    """Uniform API error envelope used for all handled failures."""

    request_id: str = Field(
        min_length=1,
        max_length=128,
        description="Correlation identifier for the failed request.",
    )
    error: ErrorDetail = Field(description="Structured error information.")
