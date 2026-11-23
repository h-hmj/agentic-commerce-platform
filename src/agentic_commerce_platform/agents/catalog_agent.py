"""Catalog search agent backed by an injected repository port."""

from __future__ import annotations

from typing import Any

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.domain.agent_models import (
    CatalogFilters,
    CatalogInput,
    CatalogOutput,
)
from agentic_commerce_platform.domain.models import AgentResult
from agentic_commerce_platform.domain.ports import CatalogRepository
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider

__all__ = ["CatalogAgent"]


class CatalogAgent(BaseAgent):
    """Validate catalog filters, query a repository, and apply the result limit.

    All matching is delegated to the injected repository. Core search behavior
    is deterministic and does not depend on LLM output; the provider is accepted
    as part of the uniform agent dependency contract for future explanation.
    """

    def __init__(
        self,
        catalog_repository: CatalogRepository,
        llm_provider: LLMProvider,
        *,
        name: str = "catalog_agent",
        timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize the agent with an injected catalog and LLM provider."""
        self._catalog_repository = catalog_repository
        self._llm_provider = llm_provider
        super().__init__(name=name, timeout_seconds=timeout_seconds)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Search the catalog using a :class:`CatalogInput` request."""
        request = kwargs.get("request")
        if not isinstance(request, CatalogInput):
            raise ValueError("CatalogAgent requires a CatalogInput via 'request'")

        category = request.category.strip() if request.category else None
        matches = self._catalog_repository.search(
            query=request.query,
            category=category,
            min_price=request.min_price,
            max_price=request.max_price,
        )
        matched_count = len(matches)
        limited_products = matches[: request.limit]
        output = CatalogOutput(
            products=limited_products,
            matched_count=matched_count,
            query=request.query.strip(),
            filters=CatalogFilters(
                query=request.query.strip(),
                category=category,
                min_price=request.min_price,
                max_price=request.max_price,
            ),
            source=self._catalog_repository.source,
        )
        return AgentResult(
            agent_name=self.name,
            success=True,
            data=output.model_dump(mode="json"),
        )
