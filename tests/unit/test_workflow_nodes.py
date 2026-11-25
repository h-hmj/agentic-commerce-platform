"""Tests for each phase-three LangGraph node using real offline agents."""

from __future__ import annotations

from typing import Any

from agentic_commerce_platform.domain.enums import WorkflowStatus
from agentic_commerce_platform.orchestration.state import (
    RecommendationWorkflowState,
    merge_agent_results,
    merge_unique_strings,
)
from tests.workflow_helpers import (
    make_initial_state,
    make_workflow_nodes,
)


def _merge(
    state: RecommendationWorkflowState,
    update: RecommendationWorkflowState,
) -> RecommendationWorkflowState:
    """Apply a node update with the same reducers used by LangGraph."""
    merged = dict(state)
    for key, value in update.items():
        if key == "agent_results":
            merged[key] = merge_agent_results(
                merged.get("agent_results"), value  # type: ignore[arg-type]
            )
        elif key in {"errors", "warnings"}:
            merged[key] = merge_unique_strings(
                merged.get(key), value  # type: ignore[arg-type]
            )
        else:
            merged[key] = value
    return RecommendationWorkflowState(**merged)


async def _state_through(
    nodes: Any,
    *node_names: str,
) -> RecommendationWorkflowState:
    """Run selected real nodes sequentially for focused node tests."""
    state = _merge(make_initial_state(), await nodes.initialize_request_node(make_initial_state()))
    sequence = {
        "profile": nodes.user_profile_node,
        "catalog": nodes.catalog_node,
        "recommendation": nodes.recommendation_node,
        "inventory": nodes.inventory_node,
        "filter": nodes.inventory_filter_node,
        "marketing": nodes.marketing_node,
        "aggregate": nodes.aggregate_node,
    }
    for node_name in node_names:
        state = _merge(state, await sequence[node_name](state))
    return state


async def test_initialize_request_node(test_settings) -> None:
    """Initialization sets request ID, counters, timestamps, and running status."""
    nodes = make_workflow_nodes(test_settings)
    initial = make_initial_state(request_id="")

    updates = await nodes.initialize_request_node(initial)

    assert updates["request_id"]
    assert updates["workflow_status"] is WorkflowStatus.RUNNING
    assert updates["current_node"] == "initialize_request"
    assert updates["started_at"]
    assert updates["started_at_monotonic"] > 0
    assert updates["completed_at"] is None
    assert updates["agent_results"] == {}
    assert updates["errors"] == []
    assert updates["warnings"] == []


async def test_user_profile_node(test_settings) -> None:
    """Profile node records the agent result and structured profile."""
    nodes = make_workflow_nodes(test_settings)
    state = _merge(
        make_initial_state(),
        await nodes.initialize_request_node(make_initial_state()),
    )

    updates = await nodes.user_profile_node(state)

    assert updates["user_profile"] is not None
    assert updates["user_profile"].user_id == "u-demo-001"
    assert updates["user_profile_input"].user_id == "u-demo-001"
    assert "user_profile_agent" in updates["agent_results"]
    assert updates["agent_results"]["user_profile_agent"].success is True


async def test_catalog_node(test_settings) -> None:
    """Catalog node records structured candidates and its agent result."""
    nodes = make_workflow_nodes(test_settings)
    state = _merge(
        make_initial_state(),
        await nodes.initialize_request_node(make_initial_state()),
    )

    updates = await nodes.catalog_node(state)

    assert updates["catalog_input"] is not None
    assert updates["candidate_products"]
    assert "catalog_agent" in updates["agent_results"]
    assert updates["agent_results"]["catalog_agent"].success is True


async def test_recommendation_node(test_settings) -> None:
    """Recommendation node joins profile/catalog outputs into ranked products."""
    nodes = make_workflow_nodes(test_settings)
    state = await _state_through(nodes, "profile", "catalog")

    updates = await nodes.recommendation_node(state)

    assert updates["recommendation_input"] is not None
    assert updates["ranked_products"]
    assert "recommendation_agent" in updates["agent_results"]
    assert updates["current_node"] == "recommendation"


async def test_inventory_node(test_settings) -> None:
    """Inventory node records available, unavailable, and alert state."""
    nodes = make_workflow_nodes(test_settings)
    state = await _state_through(nodes, "profile", "catalog", "recommendation")

    updates = await nodes.inventory_node(state)

    assert updates["inventory_input"] is not None
    assert updates["available_products"]
    assert updates["unavailable_products"] == []
    assert updates["inventory_alerts"] == []
    assert "inventory_agent" in updates["agent_results"]


async def test_inventory_filter_node_preserves_ranked_order(test_settings) -> None:
    """Filtering keeps recommendation order and removes unavailable products."""
    nodes = make_workflow_nodes(test_settings)
    state = await _state_through(
        nodes,
        "profile",
        "catalog",
        "recommendation",
        "inventory",
    )

    updates = await nodes.inventory_filter_node(state)

    ranked_ids = [product.product_id for product in state["ranked_products"]]
    filtered_ids = [product.product_id for product in updates["available_products"]]
    assert filtered_ids == [pid for pid in ranked_ids if pid in set(filtered_ids)]
    assert updates["final_product_count"] == len(filtered_ids)


async def test_marketing_node_uses_only_final_products(test_settings) -> None:
    """Marketing receives exactly the filtered product IDs and returns copies."""
    nodes = make_workflow_nodes(test_settings)
    state = await _state_through(
        nodes,
        "profile",
        "catalog",
        "recommendation",
        "inventory",
        "filter",
    )

    updates = await nodes.marketing_node(state)

    final_ids = {product.product_id for product in state["available_products"]}
    assert updates["marketing_input"] is not None
    assert {copy.product_id for copy in updates["marketing_copies"]} <= final_ids
    assert "marketing_agent" in updates["agent_results"]


async def test_aggregate_node_finishes_successful_workflow(test_settings) -> None:
    """Aggregation computes latency and final success status."""
    nodes = make_workflow_nodes(test_settings)
    state = await _state_through(
        nodes,
        "profile",
        "catalog",
        "recommendation",
        "inventory",
        "filter",
        "marketing",
    )

    updates = await nodes.aggregate_node(state)

    assert updates["workflow_status"] is WorkflowStatus.SUCCESS
    assert updates["completed_at"]
    assert updates["total_latency_ms"] >= 0.0
    assert updates["final_product_count"] == len(state["available_products"])
    assert updates["current_node"] == "aggregate"
