"""Small deterministic factories shared by phase-two tests."""

from __future__ import annotations

from decimal import Decimal
from typing import TypeVar

from pydantic import BaseModel

from agentic_commerce_platform.domain.agent_models import PriceRange, UserProfileOutput
from agentic_commerce_platform.domain.enums import (
    DataSource,
    ProfileSource,
    UserSegment,
)
from agentic_commerce_platform.domain.models import AgentResult, Product

_OutputT = TypeVar("_OutputT", bound=BaseModel)


def make_product(
    product_id: str = "p-1",
    *,
    name: str | None = None,
    category: str = "books",
    price: str = "99.00",
    stock: int = 10,
    tags: list[str] | None = None,
) -> Product:
    """Build a deterministic phase-two test product."""
    return Product(
        product_id=product_id,
        name=name or f"Product {product_id}",
        category=category,
        price=Decimal(price),
        stock=stock,
        tags=tags if tags is not None else ["python"],
    )


def make_profile(
    *,
    segments: list[UserSegment] | None = None,
    preferred_categories: list[str] | None = None,
    min_price: str = "0.00",
    max_price: str | None = None,
    recent_interests: list[str] | None = None,
    confidence: float = 0.8,
) -> UserProfileOutput:
    """Build a validated profile for recommendation and marketing tests."""
    return UserProfileOutput(
        user_id="u-test",
        segments=segments or [UserSegment.ACTIVE],
        preferred_categories=preferred_categories or [],
        price_range=PriceRange(
            min_price=Decimal(min_price),
            max_price=Decimal(max_price) if max_price is not None else None,
        ),
        recent_interests=recent_interests or [],
        confidence=confidence,
        profile_source=ProfileSource.RULE_BASED,
        data_source=DataSource.IN_MEMORY_DEMO,
    )


def parse_output(result: AgentResult, output_type: type[_OutputT]) -> _OutputT:
    """Assert a successful agent result and validate its structured payload."""
    assert result.success is True, result.error
    return output_type.model_validate(result.data)
