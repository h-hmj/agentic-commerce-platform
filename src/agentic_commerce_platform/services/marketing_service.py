"""Service for invoking the marketing copy agent independently."""

from __future__ import annotations

from agentic_commerce_platform.agents.marketing_agent import MarketingAgent
from agentic_commerce_platform.domain.agent_models import MarketingInput, MarketingOutput
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider
from agentic_commerce_platform.services.agent_runner import run_agent_for_output

__all__ = ["MarketingService"]


class MarketingService:
    """Call the marketing agent with an injected LLM provider."""

    def __init__(self, llm_provider: LLMProvider) -> None:
        """Create the service and inject its agent dependency."""
        self._agent = MarketingAgent(llm_provider)

    @property
    def agent(self) -> MarketingAgent:
        """Return the service-owned agent for introspection in tests."""
        return self._agent

    async def generate_copies(self, request: MarketingInput) -> MarketingOutput:
        """Generate copy for one validated product set."""
        return await run_agent_for_output(self._agent, request, MarketingOutput)
