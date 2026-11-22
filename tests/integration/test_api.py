"""HTTP integration tests for the phase-one FastAPI application."""

from __future__ import annotations

import socket

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ecommerce_platform.api.dependencies import get_recommendation_service
from ecommerce_platform.infrastructure.llm import MockLLMProvider
from ecommerce_platform.services.recommendation_service import RecommendationService


def test_health_endpoint(client: TestClient) -> None:
    """Health returns configured metadata and a correlation header."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "app_name": "multi-agent-ecommerce-platform",
        "version": "0.1.0",
        "environment": "test",
    }
    assert response.headers["X-Request-ID"]


def test_recommend_endpoint_returns_skeleton(client: TestClient) -> None:
    """The recommendation route returns the explicit phase-one skeleton."""
    response = client.post(
        "/api/v1/recommend",
        json={
            "user_id": "demo-user",
            "scene": "home",
            "num_items": 3,
            "context": {
                "device_type": "mobile",
                "locale": "zh-CN",
                "keywords": ["python"],
            },
        },
        headers={"X-Request-ID": "integration-request-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "integration-request-1"
    assert response.headers["X-Request-ID"] == "integration-request-1"
    assert body["user_id"] == "demo-user"
    assert body["status"] == "skeleton"
    assert body["products"] == []
    assert body["total_latency_ms"] >= 0.0
    assert body["messages"] == [
        "阶段一工程骨架已运行，真实推荐流程将在后续阶段实现。",
        "当前使用 DemoAgent 与 MockLLMProvider，响应不是真实商品推荐。",
    ]
    assert set(body["agent_results"]) == {"demo_agent"}
    assert body["agent_results"]["demo_agent"]["success"] is True
    assert body["agent_results"]["demo_agent"]["data"]["demo"] is True
    assert "MOCK" in body["agent_results"]["demo_agent"]["data"]["llm_output"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"user_id": ""},
        {"user_id": "demo-user", "num_items": 0},
        {"user_id": "demo-user", "scene": "not-a-scene"},
        {"user_id": "demo-user", "context": {"secret_free_text": "should be rejected"}},
    ],
)
def test_invalid_recommendation_requests_return_422(
    client: TestClient,
    payload: dict[str, object],
) -> None:
    """Request validation errors use the stable ErrorResponse envelope."""
    response = client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["request_id"]
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["message"] == "请求参数校验失败。"
    assert isinstance(body["error"]["details"]["errors"], list)
    assert "Traceback" not in response.text
    assert "should be rejected" not in response.text


def test_agent_failure_returns_stable_502(app: FastAPI) -> None:
    """Agent failures are translated without leaking internal exception text."""
    failing_service = RecommendationService(
        MockLLMProvider(fail=True, failure_message="simulated provider outage")
    )
    app.dependency_overrides[get_recommendation_service] = lambda: failing_service

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/v1/recommend",
                json={"user_id": "demo-user"},
                headers={"X-Request-ID": "failure-request-1"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.headers["X-Request-ID"] == "failure-request-1"
    body = response.json()
    assert body["request_id"] == "failure-request-1"
    assert body["error"]["code"] == "agent_execution_error"
    assert body["error"]["message"] == "推荐 Agent 执行失败，请稍后重试。"
    assert "simulated provider outage" not in response.text
    assert "Traceback" not in response.text


def test_requests_work_when_outbound_network_is_blocked(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase-one endpoints make no outbound socket connections."""

    def block_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("outbound network access attempted")

    monkeypatch.setattr(socket, "create_connection", block_network)

    health_response = client.get("/health")
    recommendation_response = client.post(
        "/api/v1/recommend",
        json={"user_id": "offline-user"},
    )

    assert health_response.status_code == 200
    assert recommendation_response.status_code == 200
    assert recommendation_response.json()["status"] == "skeleton"


def test_unknown_route_uses_stable_error_envelope(client: TestClient) -> None:
    """Framework 404s share the same error contract as business failures."""
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"] == "请求的资源不存在。"
