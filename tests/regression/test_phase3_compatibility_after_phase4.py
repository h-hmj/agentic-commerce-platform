"""Phase-three workflow behavior remains compatible after phase-four adapters."""

from __future__ import annotations

from tests.workflow_helpers import make_request, make_supervisor


async def test_phase3_supervisor_without_phase4_services_still_succeeds(
    test_settings,
) -> None:
    """The phase-three graph still runs with its original in-memory dependencies."""
    supervisor = make_supervisor(test_settings)

    response = await supervisor.run(
        make_request(query="python", category="books", num_items=2),
        request_id="phase3-regression",
    )

    assert response.status.value == "success"
    assert response.workflow_status.value == "success"
    assert response.products
    assert response.marketing_copies
    assert response.data_source.value == "in_memory_demo"
    assert response.embedding_provider == "deterministic"
    assert set(response.agent_results) >= {
        "user_profile_agent",
        "catalog_agent",
        "recommendation_agent",
        "inventory_agent",
        "marketing_agent",
    }
