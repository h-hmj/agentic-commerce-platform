"""Validation tests for the Pydantic domain contracts."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from ecommerce_platform.domain.enums import RecommendationScene, RecommendationStatus
from ecommerce_platform.domain.models import (
    AgentResult,
    ErrorDetail,
    ErrorResponse,
    Product,
    RecommendationContext,
    RecommendationRequest,
    RecommendationResponse,
)


def test_recommendation_request_accepts_valid_input() -> None:
    """A normal request fills defaults and preserves structured context."""
    request = RecommendationRequest(
        user_id="user-123",
        scene=RecommendationScene.PRODUCT_DETAIL,
        num_items=5,
        context=RecommendationContext(
            device_type="mobile",
            locale="zh-CN",
            category="books",
            keywords=["python", "architecture"],
        ),
    )

    assert request.user_id == "user-123"
    assert request.scene is RecommendationScene.PRODUCT_DETAIL
    assert request.num_items == 5
    assert request.context.keywords == ["python", "architecture"]


def test_recommendation_request_defaults() -> None:
    """Only user_id is required and scene defaults to home."""
    request = RecommendationRequest(user_id="demo-user")

    assert request.scene is RecommendationScene.HOME
    assert request.num_items == 10
    assert request.context.locale == "zh-CN"
    assert request.context.keywords == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"user_id": ""},
        {"user_id": "   "},
        {"user_id": "u1", "num_items": 0},
        {"user_id": "u1", "num_items": 51},
        {"user_id": "u1", "scene": "unknown-scene"},
        {"user_id": "u1", "context": {"unexpected": "value"}},
        {"user_id": "u1", "context": {"keywords": ["   "]}},
    ],
)
def test_recommendation_request_rejects_invalid_input(
    payload: dict[str, object],
) -> None:
    """Invalid identifiers, ranges, scenes, and contexts fail validation."""
    with pytest.raises(ValidationError):
        RecommendationRequest(**payload)


def test_product_accepts_valid_fields() -> None:
    """A product with non-negative values validates."""
    product = Product(
        product_id="p-1",
        name="Clean Architecture",
        category="books",
        price=Decimal("39.90"),
        stock=12,
        tags=["architecture", "software"],
    )

    assert product.price == Decimal("39.90")
    assert product.stock == 12
    assert product.tags == ["architecture", "software"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"product_id": ""},
        {"product_id": "   "},
        {"name": ""},
        {"category": "  "},
        {"price": Decimal("-0.01")},
        {"stock": -1},
        {"tags": [""]},
    ],
)
def test_product_rejects_invalid_fields(overrides: dict[str, object]) -> None:
    """Required text and non-negative numeric constraints are enforced."""
    payload: dict[str, object] = {
        "product_id": "p-1",
        "name": "Example product",
        "category": "books",
        "price": Decimal("10.00"),
        "stock": 1,
        "tags": ["example"],
    }
    payload.update(overrides)

    with pytest.raises(ValidationError):
        Product(**payload)


def test_agent_result_success_and_failure_contracts() -> None:
    """Agent results carry confidence and require a reason on failure."""
    success = AgentResult(
        agent_name="demo_agent",
        success=True,
        latency_ms=1.25,
        confidence=0.0,
        data={"demo": True},
    )
    failure = AgentResult(
        agent_name="demo_agent",
        success=False,
        latency_ms=2.5,
        error="RuntimeError: boom",
    )

    assert success.error is None
    assert success.confidence == 0.0
    assert failure.success is False
    assert failure.error == "RuntimeError: boom"


@pytest.mark.parametrize(
    "payload",
    [
        {"agent_name": "", "success": True},
        {"agent_name": "agent", "success": False},
        {"agent_name": "agent", "success": True, "error": "not allowed"},
        {"agent_name": "agent", "success": True, "latency_ms": -1},
        {"agent_name": "agent", "success": True, "confidence": 1.1},
        {"agent_name": "agent", "success": True, "confidence": -0.1},
    ],
)
def test_agent_result_rejects_invalid_contracts(payload: dict[str, object]) -> None:
    """Inconsistent and out-of-range agent results are rejected."""
    with pytest.raises(ValidationError):
        AgentResult(**payload)


def test_recommendation_response_and_error_envelope_validate() -> None:
    """Response and error envelopes accept the shapes exposed by the API."""
    agent_result = AgentResult(
        agent_name="demo_agent",
        success=True,
        latency_ms=1.0,
        data={"demo": True},
    )
    response = RecommendationResponse(
        request_id="req-1",
        user_id="demo-user",
        status=RecommendationStatus.SKELETON,
        products=[],
        messages=["阶段一骨架"],
        agent_results={"demo_agent": agent_result},
        total_latency_ms=1.0,
    )
    error = ErrorResponse(
        request_id="req-1",
        error=ErrorDetail(
            code="validation_error",
            message="请求参数校验失败。",
            details={"errors": []},
        ),
    )

    assert response.status is RecommendationStatus.SKELETON
    assert response.agent_results["demo_agent"].success is True
    assert error.error.code == "validation_error"
    assert ErrorResponse.model_validate(error.model_dump()).request_id == "req-1"
