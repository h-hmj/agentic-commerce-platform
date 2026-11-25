"""LangGraph StateGraph construction for the multi-agent recommendation flow."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agentic_commerce_platform.orchestration.nodes import WorkflowNodes
from agentic_commerce_platform.orchestration.routing import (
    route_after_inventory_filter,
    route_after_recommendation,
)
from agentic_commerce_platform.orchestration.state import RecommendationWorkflowState

__all__ = ["GRAPH_EDGES", "GRAPH_NODE_NAMES", "build_recommendation_graph"]

GRAPH_NODE_NAMES: tuple[str, ...] = (
    "initialize_request",
    "user_profile",
    "catalog",
    "recommendation",
    "inventory",
    "inventory_filter",
    "marketing",
    "aggregate",
)

# Static and conditional edges are documented here for tests and architecture
# reviews. Conditional targets are represented by their possible destinations.
GRAPH_EDGES: tuple[tuple[str, str], ...] = (
    ("__start__", "initialize_request"),
    ("initialize_request", "user_profile"),
    ("initialize_request", "catalog"),
    ("user_profile", "recommendation"),
    ("catalog", "recommendation"),
    ("recommendation", "inventory"),
    ("recommendation", "aggregate"),
    ("inventory", "inventory_filter"),
    ("inventory_filter", "marketing"),
    ("inventory_filter", "aggregate"),
    ("marketing", "aggregate"),
    ("aggregate", "__end__"),
)


def build_recommendation_graph(nodes: WorkflowNodes) -> CompiledStateGraph:
    """Build and compile the real LangGraph recommendation workflow.

    Args:
        nodes: Node callables bound to the five injected agents.

    Returns:
        A compiled LangGraph graph. The graph executes profile and catalog
        branches in parallel after initialization, joins them before ranking,
        then follows the inventory/filter/marketing/aggregate path.
    """
    builder = StateGraph(RecommendationWorkflowState)

    builder.add_node("initialize_request", nodes.initialize_request_node)
    builder.add_node("user_profile", nodes.user_profile_node)
    builder.add_node("catalog", nodes.catalog_node)
    builder.add_node("recommendation", nodes.recommendation_node)
    builder.add_node("inventory", nodes.inventory_node)
    builder.add_node("inventory_filter", nodes.inventory_filter_node)
    builder.add_node("marketing", nodes.marketing_node)
    builder.add_node("aggregate", nodes.aggregate_node)

    builder.add_edge(START, "initialize_request")
    # Fan-out: both branches execute in the same LangGraph superstep.
    builder.add_edge("initialize_request", "user_profile")
    builder.add_edge("initialize_request", "catalog")
    # Fan-in: recommendation waits for both parallel branches.
    builder.add_edge("user_profile", "recommendation")
    builder.add_edge("catalog", "recommendation")

    builder.add_conditional_edges(
        "recommendation",
        route_after_recommendation,
        {
            "inventory": "inventory",
            "aggregate": "aggregate",
        },
    )
    builder.add_edge("inventory", "inventory_filter")
    builder.add_conditional_edges(
        "inventory_filter",
        route_after_inventory_filter,
        {
            "marketing": "marketing",
            "aggregate": "aggregate",
        },
    )
    builder.add_edge("marketing", "aggregate")
    builder.add_edge("aggregate", END)

    return builder.compile()
