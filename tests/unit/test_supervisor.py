"""Tests for Supervisor dependency injection and full workflow execution."""

from __future__ import annotations

from agentic_commerce_platform.domain.enums import (
    DataSource,
    RecommendationStatus,
    WorkflowStatus,
)
from agentic_commerce_platform.orchestration.supervisor import SupervisorOrchestrator
from tests.helpers import make_product, make_profile
from tests.workflow_helpers import (
    ConcurrencyTracker,
    FixedResultAgent,
    SlowFixedAgent,
    agent_result,
    make_catalog_output,
    make_request,
    make_supervisor,
)


async def test_supervisor_receives_five_agents_and_repositories(test_settings) -> None:
    """Supervisor dependencies are explicit and inspectable, not hidden globals."""
    supervisor = make_supervisor(test_settings)

    assert isinstance(supervisor, SupervisorOrchestrator)
    assert set(supervisor.agents) == {
        "user_profile_agent",
        "catalog_agent",
        "recommendation_agent",
        "inventory_agent",
        "marketing_agent",
    }
    assert supervisor.repositories.user_behavior is not None
    assert supervisor.repositories.catalog is not None
    assert supervisor.repositories.inventory is not None
    assert supervisor.llm_provider is not None
    assert supervisor.settings is test_settings
    assert supervisor.graph is not None


def test_supervisor_uses_the_exact_injected_agents(test_settings) -> None:
    """The compiled workflow receives the injected objects, not hidden clones."""
    fakes = {
        name: FixedResultAgent(
            name,
            agent_result(name, success=True, data={}),
        )
        for name in (
            "user_profile_agent",
            "catalog_agent",
            "recommendation_agent",
            "inventory_agent",
            "marketing_agent",
        )
    }

    supervisor = make_supervisor(test_settings, agent_overrides=fakes)

    assert supervisor.agents == fakes
    assert all(supervisor.agents[name] is fakes[name] for name in fakes)


async def test_supervisor_runs_full_workflow(test_settings) -> None:
    """A normal request runs all five agents and returns aggregated data."""
    supervisor = make_supervisor(test_settings)

    response = await supervisor.run(
        make_request(user_id="u-demo-001", query="python", num_items=3),
        request_id="supervisor-full-1",
    )

    assert response.request_id == "supervisor-full-1"
    assert response.status is RecommendationStatus.SUCCESS
    assert response.workflow_status is WorkflowStatus.SUCCESS
    assert response.products
    assert set(response.agent_results) == {
        "user_profile_agent",
        "catalog_agent",
        "recommendation_agent",
        "inventory_agent",
        "marketing_agent",
    }
    assert all(result.success for result in response.agent_results.values())
    assert response.data_source is DataSource.IN_MEMORY_DEMO
    assert response.llm_provider == "mock"
    assert response.errors == []
    assert response.messages


async def test_supervisor_run_workflow_returns_typed_state(test_settings) -> None:
    """The raw workflow state has lifecycle timestamps and final products."""
    supervisor = make_supervisor(test_settings)

    state = await supervisor.run_workflow(
        make_request(user_id="u-demo-001", query="python", num_items=2),
        request_id="supervisor-state-1",
    )

    assert state["request_id"] == "supervisor-state-1"
    assert state["workflow_status"] is WorkflowStatus.SUCCESS
    assert state["started_at"]
    assert state["completed_at"]
    assert state["total_latency_ms"] >= 0.0
    assert state["final_product_count"] == len(state["available_products"])
    assert "llm_api_key" not in state


async def test_profile_and_catalog_nodes_execute_concurrently(test_settings) -> None:
    """Real LangGraph fan-out overlaps the profile and catalog branches."""
    tracker = ConcurrencyTracker()
    profile = make_profile(
        segments=[],
        preferred_categories=["books"],
        min_price="0",
        max_price="200",
        recent_interests=["python"],
    )
    catalog_product = make_product(
        "p-001",
        name="Python 编程实战",
        category="books",
        price="89.00",
        stock=12,
        tags=["python"],
    )
    fake_profile = SlowFixedAgent(
        "user_profile_agent",
        agent_result(
            "user_profile_agent",
            success=True,
            data=profile.model_dump(mode="json"),
            confidence=profile.confidence,
        ),
        delay_seconds=0.03,
        tracker=tracker,
    )
    fake_catalog = SlowFixedAgent(
        "catalog_agent",
        agent_result(
            "catalog_agent",
            success=True,
            data=make_catalog_output([catalog_product]).model_dump(mode="json"),
        ),
        delay_seconds=0.03,
        tracker=tracker,
    )
    supervisor = make_supervisor(
        test_settings,
        agent_overrides={
            "user_profile_agent": fake_profile,
            "catalog_agent": fake_catalog,
        },
    )

    response = await supervisor.run(make_request(query="", num_items=1))

    assert tracker.max_active >= 2
    assert "user_profile_agent" in response.agent_results
    assert "catalog_agent" in response.agent_results
    assert response.products


async def test_supervisor_generates_request_id_when_missing(test_settings) -> None:
    """A caller-supplied blank/none request ID is replaced in the state."""
    supervisor = make_supervisor(test_settings)

    state = await supervisor.run_workflow(make_request(query="python"), request_id=None)

    assert state["request_id"]
    assert len(state["request_id"]) == 32
