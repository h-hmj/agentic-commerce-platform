"""Tests for the phase-three workflow state contract and merge rules."""

from __future__ import annotations

from agentic_commerce_platform.domain.agent_models import CatalogInput, UserProfileInput
from agentic_commerce_platform.domain.enums import WorkflowStatus
from agentic_commerce_platform.domain.models import AgentResult
from agentic_commerce_platform.orchestration.state import (
    RecommendationWorkflowState,
    build_initial_workflow_state,
    merge_agent_results,
    merge_unique_strings,
)
from tests.workflow_helpers import make_request


def test_initial_state_contains_input_fields_and_no_secrets() -> None:
    """Initial state carries only validated request data and no credentials."""
    request = make_request(user_id="u-1", query="python", num_items=4)

    state = build_initial_workflow_state(request, "request-123")

    assert state["request_id"] == "request-123"
    assert state["user_id"] == "u-1"
    assert state["scene"] == "home"
    assert state["num_items"] == 4
    assert state["context"].keywords == ["python"]
    assert "api_key" not in state
    assert "llm_api_key" not in state
    assert "password" not in state


def test_state_contract_contains_required_phase_three_fields() -> None:
    """The TypedDict exposes all required inputs, intermediate and final fields."""
    required = {
        "request_id",
        "user_id",
        "scene",
        "num_items",
        "context",
        "user_profile_input",
        "user_profile",
        "catalog_input",
        "candidate_products",
        "recommendation_input",
        "ranked_products",
        "inventory_input",
        "available_products",
        "unavailable_products",
        "inventory_alerts",
        "marketing_input",
        "marketing_copies",
        "agent_results",
        "errors",
        "warnings",
        "current_node",
        "workflow_status",
        "started_at",
        "completed_at",
        "total_latency_ms",
    }

    assert required <= set(RecommendationWorkflowState.__annotations__)


def test_state_can_hold_agent_results_and_structured_inputs() -> None:
    """Structured agent inputs and results remain strongly typed in state."""
    state = RecommendationWorkflowState(
        request_id="r-1",
        user_id="u-1",
        user_profile_input=UserProfileInput(user_id="u-1"),
        catalog_input=CatalogInput(query="python"),
        workflow_status=WorkflowStatus.RUNNING,
        agent_results={},
        errors=[],
        warnings=[],
    )

    assert isinstance(state["user_profile_input"], UserProfileInput)
    assert isinstance(state["catalog_input"], CatalogInput)
    assert state["workflow_status"] is WorkflowStatus.RUNNING


def test_agent_result_reducer_preserves_both_parallel_branches() -> None:
    """Parallel profile and catalog results are merged, not overwritten."""
    profile_result = AgentResult(
        agent_name="user_profile_agent",
        success=True,
        data={"ok": True},
    )
    catalog_result = AgentResult(
        agent_name="catalog_agent",
        success=True,
        data={"products": []},
    )

    merged = merge_agent_results(
        {"user_profile_agent": profile_result},
        {"catalog_agent": catalog_result},
    )

    assert set(merged) == {"user_profile_agent", "catalog_agent"}
    assert merged["user_profile_agent"] is profile_result
    assert merged["catalog_agent"] is catalog_result


def test_warning_reducer_deduplicates_and_preserves_order() -> None:
    """Parallel warning lists are combined deterministically."""
    merged = merge_unique_strings(["first", "second"], ["second", "third"])

    assert merged == ["first", "second", "third"]
    assert merge_unique_strings(None, ["only"]) == ["only"]
