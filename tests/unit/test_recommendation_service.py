"""Tests for phase-one RecommendationService behavior."""

from __future__ import annotations

import pytest

from agentic_commerce_platform.domain.enums import RecommendationScene, RecommendationStatus
from agentic_commerce_platform.domain.errors import AgentExecutionError
from agentic_commerce_platform.domain.models import RecommendationRequest
from agentic_commerce_platform.infrastructure.llm import MockLLMProvider
from agentic_commerce_platform.services.recommendation_service import RecommendationService


async def test_service_returns_explicit_skeleton_response() -> None:
    """The service calls the demo agent but returns no real products."""
    service = RecommendationService(MockLLMProvider())
    request = RecommendationRequest(
        user_id="demo-user",
        scene=RecommendationScene.HOME,
        num_items=3,
    )

    response = await service.recommend(request, request_id="test-request-id")

    assert response.request_id == "test-request-id"
    assert response.user_id == "demo-user"
    assert response.status is RecommendationStatus.SKELETON
    assert response.products == []
    assert response.total_latency_ms >= 0.0
    assert len(response.messages) == 2
    assert "阶段一工程骨架" in response.messages[0]
    assert "不是真实商品推荐" in response.messages[1]
    assert "demo_agent" in response.agent_results

    agent_result = response.agent_results["demo_agent"]
    assert agent_result.success is True
    assert agent_result.confidence is None
    assert agent_result.data["demo"] is True
    assert agent_result.data["provider"] == "mock"
    assert "MOCK" in agent_result.data["llm_output"]


async def test_service_generates_unique_request_ids_when_omitted() -> None:
    """The service creates a fresh correlation ID per call."""
    service = RecommendationService(MockLLMProvider())
    request = RecommendationRequest(user_id="demo-user")

    first = await service.recommend(request)
    second = await service.recommend(request)

    assert first.request_id
    assert second.request_id
    assert first.request_id != second.request_id
    assert len(first.request_id) == 32


async def test_service_translates_agent_failure_to_agent_execution_error() -> None:
    """Provider failure is surfaced as a project-level agent failure."""
    service = RecommendationService(MockLLMProvider(fail=True))
    request = RecommendationRequest(user_id="demo-user")

    with pytest.raises(AgentExecutionError) as exc_info:
        await service.recommend(request, request_id="failure-request")

    error = exc_info.value
    assert error.agent_name == "demo_agent"
    assert error.code == "agent_execution_error"
    assert "demo_agent" in str(error)
    assert error.details["agent_error"] is not None


async def test_service_rejects_injected_failed_agent_result() -> None:
    """A structurally failed agent result is not silently returned as success."""
    from typing import Any

    from agentic_commerce_platform.agents.base import BaseAgent
    from agentic_commerce_platform.domain.models import AgentResult

    class StructurallyFailingAgent(BaseAgent):
        def __init__(self) -> None:
            super().__init__(name="failing_demo", timeout_seconds=1.0)

        async def execute(self, **kwargs: Any) -> AgentResult:
            return AgentResult(
                agent_name=self.name,
                success=False,
                latency_ms=1.0,
                error="expected test failure",
            )

    service = RecommendationService(
        MockLLMProvider(),
        agent=StructurallyFailingAgent(),
    )

    with pytest.raises(AgentExecutionError) as exc_info:
        await service.recommend(
            RecommendationRequest(user_id="demo-user"),
            request_id="structural-failure",
        )

    assert exc_info.value.agent_name == "failing_demo"
    assert exc_info.value.details["agent_error"] == "expected test failure"
