"""Tests for deterministic LangGraph conditional routing."""

from __future__ import annotations

from agentic_commerce_platform.orchestration.routing import (
    route_after_inventory_filter,
    route_after_recommendation,
)
from agentic_commerce_platform.orchestration.state import RecommendationWorkflowState
from tests.helpers import make_product


def test_recommendation_routes_to_inventory_when_ranked_products_exist() -> None:
    """A non-empty ranking continues to inventory."""
    state = RecommendationWorkflowState(
        ranked_products=[make_product("p-1")],
    )

    assert route_after_recommendation(state) == "inventory"


def test_empty_ranked_products_skip_to_aggregate() -> None:
    """Empty or all-out-of-stock ranking ends the workflow safely."""
    assert route_after_recommendation(RecommendationWorkflowState()) == "aggregate"
    assert (
        route_after_recommendation(
            RecommendationWorkflowState(ranked_products=[], failed_stage=None)
        )
        == "aggregate"
    )


def test_catalog_failure_skips_inventory_and_marketing() -> None:
    """A failed catalog must not create fake candidate rankings."""
    state = RecommendationWorkflowState(
        failed_stage="catalog",
        ranked_products=[make_product("p-1")],
    )

    assert route_after_recommendation(state) == "aggregate"


def test_recommendation_failure_skips_raw_candidates() -> None:
    """Failed ranking does not pass raw candidate products downstream."""
    state = RecommendationWorkflowState(
        failed_stage="recommendation",
        ranked_products=[make_product("p-1")],
    )

    assert route_after_recommendation(state) == "aggregate"


def test_inventory_failure_skips_marketing() -> None:
    """Inventory failure must not lead to marketing on unknown stock."""
    state = RecommendationWorkflowState(failed_stage="inventory")

    assert route_after_inventory_filter(state) == "aggregate"


def test_successful_inventory_filter_routes_to_marketing() -> None:
    """A successful filter, including an empty result, reaches marketing."""
    assert (
        route_after_inventory_filter(
            RecommendationWorkflowState(available_products=[])
        )
        == "marketing"
    )
