"""Typed state reserved for the future LangGraph recommendation workflow.

Phase one only defines this contract. No Supervisor, graph, node, or multi-agent
collaboration is implemented yet.
"""

from __future__ import annotations

from typing import TypedDict

from agentic_commerce_platform.domain.models import AgentResult, Product

__all__ = ["RecommendationState"]


class RecommendationState(TypedDict, total=False):
    """Shared state shape planned for the future LangGraph workflow.

    All keys are optional because future nodes will populate them incrementally.
    The state uses the string value of a recommendation scene so it remains easy
    to serialize in a graph checkpoint.
    """

    request_id: str
    user_id: str
    scene: str
    num_items: int
    products: list[Product]
    agent_results: dict[str, AgentResult]
    errors: list[str]
