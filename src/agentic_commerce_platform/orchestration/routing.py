"""Conditional routing rules for the phase-three workflow."""

from __future__ import annotations

from typing import Literal

from agentic_commerce_platform.orchestration.state import RecommendationWorkflowState

__all__ = ["route_after_inventory_filter", "route_after_recommendation"]


def route_after_recommendation(
    state: RecommendationWorkflowState,
) -> Literal["inventory", "aggregate"]:
    """Skip inventory when no rankings exist or recommendation failed.

    A catalog failure is fatal for ranking because inventing products is not an
    acceptable fallback. A recommendation failure similarly must not pass raw
    candidates through as if they were ranked results.
    """
    if state.get("failed_stage") in {"catalog", "recommendation"}:
        return "aggregate"
    if not state.get("ranked_products"):
        return "aggregate"
    return "inventory"


def route_after_inventory_filter(
    state: RecommendationWorkflowState,
) -> Literal["marketing", "aggregate"]:
    """Skip marketing when inventory failed; otherwise run it for final products.

    An empty-but-successful inventory result still goes through the marketing
    node, which explicitly skips copy generation when there are no products.
    """
    if state.get("failed_stage") == "inventory":
        return "aggregate"
    return "marketing"
