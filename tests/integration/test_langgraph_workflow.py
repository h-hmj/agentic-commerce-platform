"""Integration tests against the compiled LangGraph StateGraph itself."""

from __future__ import annotations

from langgraph.graph.state import CompiledStateGraph

from agentic_commerce_platform.domain.enums import WorkflowStatus
from agentic_commerce_platform.orchestration.graph import (
    GRAPH_EDGES,
    GRAPH_NODE_NAMES,
    build_recommendation_graph,
)
from tests.workflow_helpers import make_initial_state, make_workflow_nodes


def test_graph_is_a_compiled_langgraph(test_settings) -> None:
    """The project builds a real compiled LangGraph, not a plain function."""
    nodes = make_workflow_nodes(test_settings)

    graph = build_recommendation_graph(nodes)

    assert isinstance(graph, CompiledStateGraph)


def test_graph_contains_expected_nodes_and_edges(test_settings) -> None:
    """The compiled graph exposes the documented topology."""
    graph = build_recommendation_graph(make_workflow_nodes(test_settings))
    drawable = graph.get_graph()

    assert set(GRAPH_NODE_NAMES) <= set(drawable.nodes)
    actual_edges = {(edge.source, edge.target) for edge in drawable.edges}
    assert set(GRAPH_EDGES) <= actual_edges


async def test_compiled_graph_success_path(test_settings) -> None:
    """The graph executes the full success path directly."""
    graph = build_recommendation_graph(make_workflow_nodes(test_settings))

    final_state = await graph.ainvoke(
        make_initial_state(
            request_id="graph-success-1",
            user_id="u-demo-001",
            query="python",
            num_items=3,
        )
    )

    assert final_state["request_id"] == "graph-success-1"
    assert final_state["workflow_status"] is WorkflowStatus.SUCCESS
    assert final_state["available_products"]
    assert final_state["marketing_copies"]
    assert set(final_state["agent_results"]) == {
        "user_profile_agent",
        "catalog_agent",
        "recommendation_agent",
        "inventory_agent",
        "marketing_agent",
    }


async def test_compiled_graph_empty_catalog_path(test_settings) -> None:
    """A no-match catalog request degrades to a partial, empty result."""
    graph = build_recommendation_graph(make_workflow_nodes(test_settings))

    final_state = await graph.ainvoke(
        make_initial_state(
            request_id="graph-empty-1",
            query="no-such-product",
            num_items=3,
        )
    )

    assert final_state["workflow_status"] is WorkflowStatus.PARTIAL_SUCCESS
    assert final_state["available_products"] == []
    assert "catalog_returned_no_products" in final_state["warnings"]
    assert "no_candidate_products" in final_state["warnings"]


async def test_compiled_graph_all_products_out_of_stock(test_settings) -> None:
    """All out-of-stock recommendations produce no final products."""
    graph = build_recommendation_graph(make_workflow_nodes(test_settings))

    final_state = await graph.ainvoke(
        make_initial_state(
            request_id="graph-oos-1",
            query="机械",
            num_items=3,
        )
    )

    assert final_state["available_products"] == []
    assert final_state["workflow_status"] is WorkflowStatus.PARTIAL_SUCCESS
    assert final_state["ranked_products"] == []
    assert "recommendation_returned_no_products" in final_state["warnings"]
