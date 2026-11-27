"""Service for invoking the catalog/RAG search agent independently."""

from __future__ import annotations

from agentic_commerce_platform.agents.catalog_agent import CatalogAgent
from agentic_commerce_platform.domain.agent_models import CatalogInput, CatalogOutput
from agentic_commerce_platform.domain.ports import CatalogRepository, RetrievalPort
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider
from agentic_commerce_platform.services.agent_runner import run_agent_for_output

__all__ = ["CatalogService"]


class CatalogService:
    """Call the catalog agent with optional RAG retrieval and explicit port DI."""

    def __init__(
        self,
        catalog_repository: CatalogRepository,
        llm_provider: LLMProvider,
        *,
        retrieval_service: RetrievalPort | None = None,
    ) -> None:
        """Create the service and inject its agent dependencies."""
        self._agent = CatalogAgent(
            catalog_repository,
            llm_provider,
            retrieval_service=retrieval_service,
        )

    @property
    def agent(self) -> CatalogAgent:
        """Return the service-owned agent for introspection in tests."""
        return self._agent

    async def search_products(self, request: CatalogInput) -> CatalogOutput:
        """Search products for one validated filter request."""
        return await run_agent_for_output(self._agent, request, CatalogOutput)
