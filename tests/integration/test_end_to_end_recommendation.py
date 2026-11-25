"""End-to-end HTTP tests for the phase-three workflow endpoint."""

from __future__ import annotations

import socket

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentic_commerce_platform.api.dependencies import get_workflow_service
from agentic_commerce_platform.domain.agent_models import RecommendationOutput
from agentic_commerce_platform.domain.enums import RecommendationStrategy
from agentic_commerce_platform.orchestration.models import (
    WorkflowRecommendationResponse,
)
from agentic_commerce_platform.services.workflow_service import WorkflowService
from tests.helpers import make_product
from tests.workflow_helpers import (
    FixedResultAgent,
    agent_result,
    make_request,
    make_supervisor,
)

_PAYLOAD = {
    "user_id": "u-demo-001",
    "scene": "home",
    "num_items": 3,
    "context": {"keywords": ["python"], "locale": "zh-CN"},
}


def test_workflow_endpoint_returns_aggregated_demo_result(client: TestClient) -> None:
    """The workflow endpoint returns products, copies, inventory, and agents."""
    response = client.post(
        "/api/v1/workflow/recommend",
        json=_PAYLOAD,
        headers={"X-Request-ID": "api-workflow-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "api-workflow-1"
    assert body["status"] == "success"
    assert body["workflow_status"] == "success"
    assert body["products"]
    assert body["data_source"] == "in_memory_demo"
    assert body["llm_provider"] == "mock"
    assert body["total_latency_ms"] >= 0.0
    assert set(body["agent_results"]) == {
        "user_profile_agent",
        "catalog_agent",
        "recommendation_agent",
        "inventory_agent",
        "marketing_agent",
    }
    final_ids = {product["product_id"] for product in body["products"]}
    unavailable_ids = {
        product["product_id"] for product in body["unavailable_products"]
    }
    copy_ids = {copy["product_id"] for copy in body["marketing_copies"]}
    assert final_ids.isdisjoint(unavailable_ids)
    assert copy_ids <= final_ids
    assert all("copy" in copy for copy in body["marketing_copies"])
    assert "MockLLMProvider" in body["messages"][0]
    assert "Traceback" not in response.text


def test_workflow_response_validates_against_public_model(client: TestClient) -> None:
    """The HTTP payload is valid under the dedicated workflow response model."""
    response = client.post("/api/v1/workflow/recommend", json=_PAYLOAD)

    model = WorkflowRecommendationResponse.model_validate(response.json())

    assert model.products
    assert model.agent_results["marketing_agent"].success is True
    assert model.marketing_copies


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"user_id": ""},
        {"user_id": "u", "num_items": 0},
        {"user_id": "u", "context": {"unknown_field": "not allowed"}},
    ],
)
def test_workflow_endpoint_rejects_invalid_requests(
    client: TestClient,
    payload: dict[str, object],
) -> None:
    """The workflow endpoint reuses the stable 422 error contract."""
    response = client.post("/api/v1/workflow/recommend", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["request_id"]
    assert "Traceback" not in response.text


def test_workflow_endpoint_works_without_network_or_api_key(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The workflow endpoint makes no outbound network calls."""
    def block_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("outbound network access attempted")

    monkeypatch.setattr(socket, "create_connection", block_network)

    response = client.post("/api/v1/workflow/recommend", json=_PAYLOAD)

    assert response.status_code == 200
    assert response.json()["products"]


def test_agent_failure_returns_workflow_status_not_stack(
    app: FastAPI,
    test_settings,
) -> None:
    """An expected agent failure is represented in a stable response, not a stack."""
    failing_catalog = FixedResultAgent(
        "catalog_agent",
        agent_result("catalog_agent", success=False, error="catalog unavailable"),
    )
    supervisor = make_supervisor(
        test_settings,
        agent_overrides={"catalog_agent": failing_catalog},
    )
    app.dependency_overrides[get_workflow_service] = lambda: WorkflowService(supervisor)

    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/v1/workflow/recommend",
                json=_PAYLOAD,
                headers={"X-Request-ID": "api-workflow-failure"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_status"] == "failed"
    assert body["products"] == []
    assert "catalog_agent_failed" in body["errors"]
    assert "Traceback" not in response.text


def test_phase_one_skeleton_endpoint_is_unchanged(client: TestClient) -> None:
    """Adding the workflow endpoint does not alter the phase-one skeleton."""
    response = client.post(
        "/api/v1/recommend",
        json={"user_id": "compatibility-user"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "skeleton"
    assert body["products"] == []
    assert set(body["agent_results"]) == {"demo_agent"}


def test_health_still_works(client: TestClient) -> None:
    """Health remains compatible with phase one."""
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


async def test_inventory_filters_ranked_products(test_settings) -> None:
    """Ranked products unavailable in inventory never reach final response/copy."""
    available = make_product("p-001", name="Python 编程实战", stock=12)
    out_of_stock = make_product("p-003", name="机械键盘 K87", stock=0)
    recommendation_output = RecommendationOutput(
        products=[available, out_of_stock],
        ranking_reasons={"p-001": [], "p-003": []},
        strategy=RecommendationStrategy.RULE_BASED_DEMO,
        filtered_count=0,
        confidence=0.7,
    )
    fake_recommendation = FixedResultAgent(
        "recommendation_agent",
        agent_result(
            "recommendation_agent",
            success=True,
            data=recommendation_output.model_dump(mode="json"),
            confidence=0.7,
        ),
    )
    supervisor = make_supervisor(
        test_settings,
        agent_overrides={"recommendation_agent": fake_recommendation},
    )

    response = await supervisor.run(make_request(query="python", num_items=2))

    assert [product.product_id for product in response.products] == ["p-001"]
    assert [product.product_id for product in response.unavailable_products] == [
        "p-003"
    ]
    assert [copy.product_id for copy in response.marketing_copies] == ["p-001"]


async def test_explicit_state_data_flow_and_profile_influence(test_settings) -> None:
    """Profile, catalog, ranking, inventory, and marketing data flow explicitly."""
    supervisor = make_supervisor(test_settings)

    first = await supervisor.run_workflow(
        make_request(user_id="u-demo-001", query="", num_items=3),
        request_id="data-flow-user-1",
    )
    second = await supervisor.run_workflow(
        make_request(user_id="u-demo-002", query="", num_items=3),
        request_id="data-flow-user-2",
    )

    assert first["recommendation_input"].user_profile == first["user_profile"]
    assert (
        first["recommendation_input"].candidate_products
        == first["candidate_products"]
    )
    assert first["inventory_input"].products == first["ranked_products"]
    assert first["marketing_input"].products == first["available_products"]

    final_ids = [product.product_id for product in first["available_products"]]
    ranked_ids = [product.product_id for product in first["ranked_products"]]
    assert [pid for pid in ranked_ids if pid in set(final_ids)] == final_ids
    assert {copy.product_id for copy in first["marketing_copies"]} <= set(final_ids)

    first_preferences = first["user_profile"].preferred_categories
    second_preferences = second["user_profile"].preferred_categories
    assert first_preferences != second_preferences
    assert [p.product_id for p in first["available_products"]] != [
        p.product_id for p in second["available_products"]
    ]
