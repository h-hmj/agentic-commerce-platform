"""Phase-two service for the standalone product recommendation agent.

The phase-one ``RecommendationService`` remains unchanged because it backs the
public skeleton endpoint. This separate service exposes the phase-two ranking
agent without turning the API into a multi-agent workflow.
"""

from __future__ import annotations

from agentic_commerce_platform.agents.recommendation_agent import RecommendationAgent
from agentic_commerce_platform.domain.agent_models import (
    RecommendationInput,
    RecommendationOutput,
)
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider
from agentic_commerce_platform.services.agent_runner import run_agent_for_output

__all__ = ["ProductRecommendationService"]


class ProductRecommendationService:
    """Invoke rule-based ranking against externally supplied candidates."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        """Create the service and inject the agent LLM dependency."""
        self._agent = RecommendationAgent(llm_provider)

    @property
    def agent(self) -> RecommendationAgent:
        """Return the service-owned agent for introspection in tests."""
        return self._agent

    async def recommend_products(
        self,
        request: RecommendationInput,
    ) -> RecommendationOutput:
        """Rank candidates for one user profile."""
        return await run_agent_for_output(self._agent, request, RecommendationOutput)
