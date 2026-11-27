"""Workflow state provenance with real SQLite adapters and local RAG."""

from __future__ import annotations

from agentic_commerce_platform.api.composition import build_phase4_resources
from agentic_commerce_platform.domain.enums import RecommendationScene
from agentic_commerce_platform.domain.models import RecommendationContext, RecommendationRequest
from agentic_commerce_platform.infrastructure.llm.mock_provider import MockLLMProvider
from tests.phase4_helpers import make_real_settings


async def test_real_workflow_preserves_retrieval_and_profile_provenance(tmp_path) -> None:
    """The graph state records retrieval sources/scores, profile source, and data source."""
    settings = make_real_settings(tmp_path)
    resources = build_phase4_resources(settings, MockLLMProvider())
    try:
        request = RecommendationRequest(
            user_id="u-demo-001",
            scene=RecommendationScene.HOME,
            num_items=3,
            context=RecommendationContext(keywords=["python"], category="books"),
        )
        state = await resources.workflow_service.supervisor.run_workflow(request)

        assert state["data_source"] == "database"
        assert state["profile_source"] == "rule_based+mock_llm"
        assert state["memory_source"] is None
        assert state["retrieval_scores"]
        assert state["retrieval_sources"]
        assert all(
            source in {"vector", "fallback"}
            for source in state["retrieval_sources"].values()
        )
        assert state["profile_source"] == "rule_based+mock_llm"
    finally:
        await resources.memory_store.close()
        if resources.database is not None:
            resources.database.dispose()
