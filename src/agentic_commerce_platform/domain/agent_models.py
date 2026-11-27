"""Pydantic contracts for phase-two professional agents.

These models are deliberately separate from the phase-one API contracts in
``domain.models``. They describe rule-based, offline demonstration behavior and
must not be interpreted as real production e-commerce data.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import Field, field_validator, model_validator

from agentic_commerce_platform.domain.enums import (
    DataSource,
    MarketingProvider,
    MarketingStyle,
    ProfileSource,
    RecommendationReasonCode,
    RecommendationStrategy,
    UserSegment,
)
from agentic_commerce_platform.domain.models import PlatformModel, Product

__all__ = [
    "BehaviorSnapshot",
    "CatalogFilters",
    "CatalogInput",
    "CatalogOutput",
    "InventoryInput",
    "InventoryOutput",
    "LowStockAlert",
    "MarketingCopy",
    "MarketingInput",
    "MarketingOutput",
    "PriceRange",
    "RankingReason",
    "RecommendationInput",
    "RecommendationOutput",
    "UserBehaviorRecord",
    "UserProfileInput",
    "UserProfileOutput",
]


def _normalize_string_list(values: list[str], field_name: str) -> list[str]:
    """Strip, reject blanks, and deduplicate a string list in stable order."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = value.strip()
        if not stripped:
            raise ValueError(f"{field_name} must not contain blank values")
        if stripped not in seen:
            seen.add(stripped)
            cleaned.append(stripped)
    return cleaned


class BehaviorSnapshot(PlatformModel):
    """Behavior fields used by profile rules and the in-memory behavior adapter."""

    recent_views: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="Recent viewed product identifiers or interest labels.",
    )
    recent_clicks: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="Recent clicked product identifiers or interest labels.",
    )
    recent_purchases: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="Recent purchased product identifiers.",
    )
    category_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Category to interaction count mapping.",
    )
    average_order_value: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=12,
        decimal_places=2,
        description="Historical average order value in CNY, if known.",
    )
    days_since_last_active: int | None = Field(
        default=None,
        ge=0,
        le=3650,
        description="Days since the last recorded activity, if known.",
    )
    account_age_days: int | None = Field(
        default=None,
        ge=0,
        le=3650,
        description="Account age in days, if known.",
    )

    @field_validator("recent_views", "recent_clicks", "recent_purchases")
    @classmethod
    def validate_string_lists(cls, value: list[str]) -> list[str]:
        """Reject blank values and remove duplicates while preserving order."""
        return _normalize_string_list(value, "behavior list")

    @field_validator("category_counts")
    @classmethod
    def validate_category_counts(cls, value: dict[str, int]) -> dict[str, int]:
        """Reject blank category names and negative interaction counts."""
        cleaned: dict[str, int] = {}
        for category, count in value.items():
            stripped = category.strip()
            if not stripped:
                raise ValueError("category_counts keys must not be blank")
            if count < 0:
                raise ValueError("category_counts values must be non-negative")
            if stripped in cleaned:
                raise ValueError("category_counts contains duplicate categories")
            cleaned[stripped] = count
        return cleaned


class UserBehaviorRecord(BehaviorSnapshot):
    """Behavior record returned by :class:`UserBehaviorRepository`."""

    user_id: str = Field(
        min_length=1,
        max_length=128,
        description="Stable user identifier.",
    )

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, value: str) -> str:
        """Reject blank user identifiers."""
        if not value.strip():
            raise ValueError("user_id must not be blank")
        return value


class UserProfileInput(UserBehaviorRecord):
    """Input for :class:`UserProfileAgent`.

    All behavior fields are optional. The agent merges non-empty values supplied
    here over the injected in-memory behavior record, which allows independent
    testing without a hidden data source.
    """


class PriceRange(PlatformModel):
    """Price interval inferred from historical average order value."""

    min_price: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        max_digits=12,
        decimal_places=2,
        description="Inclusive lower price bound.",
    )
    max_price: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=12,
        decimal_places=2,
        description="Inclusive upper price bound; null means unbounded.",
    )

    @model_validator(mode="after")
    def validate_bounds(self) -> PriceRange:
        """Require the lower bound not to exceed the upper bound."""
        if self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must not be greater than max_price")
        return self


class UserProfileOutput(PlatformModel):
    """Structured result of the rule-based user profile agent."""

    user_id: str = Field(min_length=1, max_length=128)
    segments: list[UserSegment] = Field(min_length=1, max_length=5)
    preferred_categories: list[str] = Field(default_factory=list, max_length=5)
    price_range: PriceRange
    recent_interests: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0.0, le=1.0)
    profile_source: ProfileSource
    data_source: DataSource
    memory_source: str | None = Field(
        default=None,
        max_length=32,
        description="Where recent behavior came from: redis, database, or in_memory.",
    )
    profile_persisted: bool = Field(
        default=False,
        description="Whether this profile was persisted to long-term storage.",
    )
    explanation: str | None = Field(default=None, max_length=1200)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class CatalogInput(PlatformModel):
    """Input filters for the catalog search agent."""

    query: str = Field(
        default="",
        max_length=200,
        description="Case-insensitive keyword query; empty lists all products.",
    )
    category: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Optional case-insensitive category filter.",
    )
    min_price: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=12,
        decimal_places=2,
        description="Optional inclusive minimum price.",
    )
    max_price: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=12,
        decimal_places=2,
        description="Optional inclusive maximum price.",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of products returned.",
    )

    @model_validator(mode="after")
    def validate_price_range(self) -> CatalogInput:
        """Reject an inverted price range instead of guessing user intent."""
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price must not be greater than max_price")
        return self


class CatalogFilters(PlatformModel):
    """Normalized filters echoed by the catalog agent."""

    query: str = ""
    category: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None


class CatalogOutput(PlatformModel):
    """Structured catalog search result."""

    products: list[Product] = Field(default_factory=list)
    matched_count: int = Field(ge=0)
    query: str
    filters: CatalogFilters
    source: DataSource
    retrieval_source: str | None = Field(
        default=None,
        max_length=64,
        description="vector, database_keyword, in_memory, or fallback.",
    )
    retrieval_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Semantic retrieval scores by product ID, when available.",
    )
    retrieval_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Safe retrieval metadata such as embedding model and top_k.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal retrieval degradation warnings.",
    )


class RankingReason(PlatformModel):
    """One structured explanation for a ranked product."""

    code: RecommendationReasonCode
    message: str = Field(min_length=1, max_length=200)


class RecommendationInput(PlatformModel):
    """Input for rule-based ranking of externally supplied candidates."""

    user_profile: UserProfileOutput
    candidate_products: list[Product] = Field(default_factory=list, max_length=200)
    num_items: int = Field(default=5, ge=1, le=50)
    retrieval_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Optional semantic scores used only as an explainable tie-breaker.",
    )


class RecommendationOutput(PlatformModel):
    """Structured products and per-product ranking explanations."""

    products: list[Product] = Field(default_factory=list)
    ranking_reasons: dict[str, list[RankingReason]] = Field(default_factory=dict)
    strategy: RecommendationStrategy
    filtered_count: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_unique_and_explained_products(self) -> RecommendationOutput:
        """Require unique product IDs and one reason entry per returned product."""
        product_ids = [product.product_id for product in self.products]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("recommendation products must be unique")
        if set(self.ranking_reasons) != set(product_ids):
            raise ValueError("ranking_reasons must contain exactly the returned product IDs")
        return self


class InventoryInput(PlatformModel):
    """Input for inventory evaluation."""

    products: list[Product] = Field(default_factory=list, max_length=100)
    low_stock_threshold: int = Field(
        default=3,
        ge=0,
        le=100,
        description="Inclusive threshold below which stock is considered low.",
    )


class LowStockAlert(PlatformModel):
    """Alert emitted for a low-stock product."""

    product_id: str = Field(min_length=1, max_length=64)
    product_name: str = Field(min_length=1, max_length=200)
    stock: int = Field(ge=1)
    threshold: int = Field(ge=0)
    message: str = Field(min_length=1, max_length=300)


class InventoryOutput(PlatformModel):
    """Structured inventory decision result."""

    available_products: list[Product] = Field(default_factory=list)
    unavailable_products: list[Product] = Field(default_factory=list)
    low_stock_alerts: list[LowStockAlert] = Field(default_factory=list)
    purchase_limits: dict[str, int] = Field(default_factory=dict)
    unavailable_reasons: dict[str, str] = Field(default_factory=dict)
    source: DataSource

    @model_validator(mode="after")
    def validate_disjoint_products(self) -> InventoryOutput:
        """Prevent the same product from being both available and unavailable."""
        available_ids = {product.product_id for product in self.available_products}
        unavailable_ids = {product.product_id for product in self.unavailable_products}
        if available_ids & unavailable_ids:
            raise ValueError("a product cannot be both available and unavailable")
        if len(available_ids) != len(self.available_products):
            raise ValueError("available_products must be unique")
        if len(unavailable_ids) != len(self.unavailable_products):
            raise ValueError("unavailable_products must be unique")
        return self


class MarketingInput(PlatformModel):
    """Input for the marketing copy agent."""

    user_profile: UserProfileOutput
    products: list[Product] = Field(default_factory=list, max_length=50)
    style: MarketingStyle | None = Field(
        default=None,
        description="Optional explicit style; otherwise derived from user segments.",
    )


class MarketingCopy(PlatformModel):
    """One product-specific marketing copy result.

    ``copy_text`` is exposed under the stable JSON alias ``copy`` so the contract
    avoids shadowing ``BaseModel.copy`` while still returning the required field.
    """

    product_id: str = Field(min_length=1, max_length=64)
    copy_text: str = Field(
        alias="copy",
        min_length=1,
        max_length=2000,
        serialization_alias="copy",
    )
    style: MarketingStyle
    compliance_passed: bool
    warnings: list[str] = Field(default_factory=list, max_length=20)
    provider: MarketingProvider


class MarketingOutput(PlatformModel):
    """Structured marketing copy result for a set of products."""

    copies: list[MarketingCopy] = Field(default_factory=list)
    style: MarketingStyle

    @model_validator(mode="after")
    def validate_copy_consistency(self) -> MarketingOutput:
        """Keep product copies unique and aligned with the selected style."""
        product_ids = [copy.product_id for copy in self.copies]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("marketing copies must contain unique product IDs")
        if any(copy.style is not self.style for copy in self.copies):
            raise ValueError("all copies must use the output style")
        return self
