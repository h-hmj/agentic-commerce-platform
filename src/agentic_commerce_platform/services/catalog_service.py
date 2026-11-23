"""Service for invoking the catalog search agent independently."""

from __future__ import annotations

from agentic_commerce_platform.agents.catalog_agent import CatalogAgent
from agentic_commerce_platform.domain.agent_models import CatalogInput, CatalogOutput
from agentic_commerce_platform.domain.ports import CatalogRepository
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider
from agentic_commerce_platform.services.agent_runner import run_agent_for_output

__all__ = ["CatalogService"]


class CatalogService:
    """Call the catalog agent through injected data and LLM dependencies."""

    def __init__(
        self,
        catalog_repository: CatalogRepository,
        llm_provider: LLMProvider,
    ) -> None:
        """Create the service and inject its agent dependencies."""
        self._agent = CatalogAgent(catalog_repository, llm_provider)

    @property
    def agent(self) -> CatalogAgent:
        """Return the service-owned agent for introspection in tests."""
        return self._agent

    async def search_products(self, request: CatalogInput) -> CatalogOutput:
        """Search products for one validated filter request."""
        return await run_agent_for_output(self._agent, request, CatalogOutput)
