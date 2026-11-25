"""Failure, degradation, and unknown-exception tests for the phase-three workflow."""

from __future__ import annotations

from agentic_commerce_platform.domain.enums import (
    RecommendationStatus,
    WorkflowStatus,
)
from tests.workflow_helpers import (
    FixedResultAgent,
    agent_result,
    make_request,
    make_supervisor,
)


async def test_profile_failure_uses_default_and_preserves_catalog_result(
    test_settings,
) -> None:
    """A profile failure degrades to a default while catalog data survives."""
    failing_profile = FixedResultAgent(
        "user_profile_agent",
        agent_result(
            "user_profile_agent",
            success=False,
            error="profile repository unavailable",
        ),
    )
    supervisor = make_supervisor(
        test_settings,
        agent_overrides={"user_profile_agent": failing_profile},
    )

    response = await supervisor.run(make_request(query="python", num_items=2))

    assert response.workflow_status is WorkflowStatus.PARTIAL_SUCCESS
    assert response.status is RecommendationStatus.PARTIAL_SUCCESS
    assert response.products
    assert response.agent_results["user_profile_agent"].success is False
    assert response.agent_results["catalog_agent"].success is True
    assert "user_profile_agent_failed" in response.errors
    assert "user_profile_fallback_default" in response.warnings


async def test_catalog_failure_returns_no_fake_products(test_settings) -> None:
    """Catalog failure terminates ranking and returns no invented products."""
    failing_catalog = FixedResultAgent(
        "catalog_agent",
        agent_result("catalog_agent", success=False, error="catalog unavailable"),
    )
    supervisor = make_supervisor(
        test_settings,
        agent_overrides={"catalog_agent": failing_catalog},
    )

    response = await supervisor.run(make_request(query="python"))

    assert response.workflow_status is WorkflowStatus.FAILED
    assert response.products == []
    assert response.agent_results["catalog_agent"].success is False
    assert response.agent_results["user_profile_agent"].success is True
    assert "catalog_agent_failed" in response.errors
    assert "marketing_agent" not in response.agent_results


async def test_recommendation_failure_does_not_pass_raw_candidates(test_settings) -> None:
    """Raw candidates are not masqueraded as ranked recommendations."""
    failing_recommendation = FixedResultAgent(
        "recommendation_agent",
        agent_result(
            "recommendation_agent",
            success=False,
            error="ranking unavailable",
        ),
    )
    supervisor = make_supervisor(
        test_settings,
        agent_overrides={"recommendation_agent": failing_recommendation},
    )

    response = await supervisor.run(make_request(query="python"))

    assert response.workflow_status is WorkflowStatus.FAILED
    assert response.products == []
    assert response.agent_results["recommendation_agent"].success is False
    assert "recommendation_agent_failed" in response.errors
    assert "inventory_agent" not in response.agent_results


async def test_inventory_failure_withholds_products(test_settings) -> None:
    """Inventory failure returns no available products and skips marketing."""
    failing_inventory = FixedResultAgent(
        "inventory_agent",
        agent_result("inventory_agent", success=False, error="inventory unavailable"),
    )
    supervisor = make_supervisor(
        test_settings,
        agent_overrides={"inventory_agent": failing_inventory},
    )

    response = await supervisor.run(make_request(query="python"))

    assert response.workflow_status is WorkflowStatus.FAILED
    assert response.products == []
    assert response.unavailable_products == []
    assert response.agent_results["inventory_agent"].success is False
    assert "inventory_agent_failed" in response.errors
    assert "inventory_failure_products_withheld" in response.warnings
    assert "marketing_agent" not in response.agent_results


async def test_marketing_failure_keeps_completed_products(test_settings) -> None:
    """Marketing failure cannot erase successful ranking and inventory results."""
    failing_marketing = FixedResultAgent(
        "marketing_agent",
        agent_result("marketing_agent", success=False, error="marketing unavailable"),
    )
    supervisor = make_supervisor(
        test_settings,
        agent_overrides={"marketing_agent": failing_marketing},
    )

    response = await supervisor.run(make_request(query="python", num_items=2))

    assert response.workflow_status is WorkflowStatus.PARTIAL_SUCCESS
    assert response.products
    assert response.marketing_copies == []
    assert response.agent_results["marketing_agent"].success is False
    assert "marketing_agent_failed" in response.errors


async def test_invalid_agent_output_is_not_trusted(test_settings) -> None:
    """A successful AgentResult with malformed data is rejected by validation."""
    malformed_catalog = FixedResultAgent(
        "catalog_agent",
        agent_result("catalog_agent", success=True, data={}),
    )
    supervisor = make_supervisor(
        test_settings,
        agent_overrides={"catalog_agent": malformed_catalog},
    )

    response = await supervisor.run(make_request(query="python"))

    assert response.workflow_status is WorkflowStatus.FAILED
    assert response.products == []
    assert "catalog_output_invalid" in response.errors
    assert response.agent_results["catalog_agent"].success is True


async def test_unknown_workflow_exception_returns_safe_failed_state(
    test_settings,
    monkeypatch,
) -> None:
    """Unexpected graph exceptions become a failed response without a stack."""
    supervisor = make_supervisor(test_settings)

    class BrokenGraph:
        async def ainvoke(self, state):
            raise RuntimeError("unexpected graph crash")

    monkeypatch.setattr(supervisor, "_graph", BrokenGraph())

    response = await supervisor.run(
        make_request(query="python"),
        request_id="workflow-crash-1",
    )

    assert response.request_id == "workflow-crash-1"
    assert response.workflow_status is WorkflowStatus.FAILED
    assert response.status is RecommendationStatus.FAILED
    assert response.products == []
    assert response.errors == ["workflow_execution_failed"]
    assert response.agent_results == {}
    assert "unexpected graph crash" not in " ".join(response.errors)


async def test_empty_catalog_is_partial_not_a_crash(test_settings) -> None:
    """An empty catalog result is distinguishable from a workflow exception."""
    supervisor = make_supervisor(test_settings)

    response = await supervisor.run(
        make_request(query="no-such-product"),
        request_id="workflow-empty-1",
    )

    assert response.workflow_status is WorkflowStatus.PARTIAL_SUCCESS
    assert response.products == []
    assert response.errors == []
    assert "catalog_returned_no_products" in response.warnings
    assert "no_candidate_products" in response.warnings
