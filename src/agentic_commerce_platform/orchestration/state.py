"""Typed state for the phase-three LangGraph recommendation workflow.

The graph uses ``Annotated`` reducers only for fields written by both parallel
branches (``agent_results``, ``errors`` and ``warnings``). Other fields have a
single writer, which makes state ownership explicit and prevents parallel nodes
from overwriting unrelated results.
"""

from __future__ import annotations

from typing import Annotated, TypedDict

from agentic_commerce_platform.domain.agent_models import (
    CatalogInput,
    InventoryInput,
    LowStockAlert,
    MarketingCopy,
    MarketingInput,
    RecommendationInput,
    UserProfileInput,
    UserProfileOutput,
)
from agentic_commerce_platform.domain.enums import WorkflowStatus
from agentic_commerce_platform.domain.models import (
    AgentResult,
    Product,
    RecommendationContext,
    RecommendationRequest,
)

__all__ = [
    "RecommendationState",
    "RecommendationWorkflowState",
    "build_initial_workflow_state",
    "merge_agent_results",
    "merge_unique_strings",
]


def merge_agent_results(
    existing: dict[str, AgentResult] | None,
    update: dict[str, AgentResult] | None,
) -> dict[str, AgentResult]:
    """Merge agent results from parallel branches without dropping either side."""
    merged = dict(existing or {})
    merged.update(update or {})
    return merged


def merge_unique_strings(
    existing: list[str] | None,
    update: list[str] | None,
) -> list[str]:
    """Merge warning/error codes in order and remove duplicates."""
    merged: list[str] = []
    for value in [*(existing or []), *(update or [])]:
        if value not in merged:
            merged.append(value)
    return merged


class RecommendationWorkflowState(TypedDict, total=False):
    """Shared state passed explicitly through every LangGraph node.

    The state contains the validated request, each agent's structured output or
    input, observability metadata, and failure/warning codes. It never contains
    an LLM API key or a raw sensitive user profile.
    """

    # Request inputs.
    request_id: str
    user_id: str
    scene: str
    num_items: int
    context: RecommendationContext

    # Agent inputs and validated outputs.
    user_profile_input: UserProfileInput | None
    user_profile: UserProfileOutput | None
    catalog_input: CatalogInput | None
    candidate_products: list[Product]
    recommendation_input: RecommendationInput | None
    ranked_products: list[Product]
    inventory_input: InventoryInput | None
    available_products: list[Product]
    unavailable_products: list[Product]
    inventory_alerts: list[LowStockAlert]
    marketing_input: MarketingInput | None
    marketing_copies: list[MarketingCopy]

    # Phase-four provenance and retrieval context.
    retrieval_sources: dict[str, str]
    retrieval_scores: dict[str, float]
    profile_source: str | None
    memory_source: str | None
    data_source: str

    # Results and observable lifecycle.
    agent_results: Annotated[dict[str, AgentResult], merge_agent_results]
    errors: Annotated[list[str], merge_unique_strings]
    warnings: Annotated[list[str], merge_unique_strings]
    current_node: str
    workflow_status: WorkflowStatus
    failed_stage: str | None
    started_at: str | None
    completed_at: str | None
    started_at_monotonic: float
    total_latency_ms: float
    final_product_count: int


# Phase-one/phase-two compatibility alias. The richer phase-three state is
# additive and does not alter any existing API or agent contract.
RecommendationState = RecommendationWorkflowState


def build_initial_workflow_state(
    request: RecommendationRequest,
    request_id: str,
) -> RecommendationWorkflowState:
    """Build the minimal state supplied to ``initialize_request_node``.

    Timestamps, collections, and workflow status are initialized by the graph
    node itself. This keeps initialization testable and ensures a missing or
    blank request ID can be replaced inside the graph.
    """
    return RecommendationWorkflowState(
        request_id=request_id,
        user_id=request.user_id,
        scene=request.scene.value,
        num_items=request.num_items,
        context=request.context,
        retrieval_sources={},
        retrieval_scores={},
        profile_source=None,
        memory_source=None,
        data_source="in_memory_demo",
    )
