"""Catalog search agent backed by structured and optional RAG retrieval."""

from __future__ import annotations

import logging
from typing import Any

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.domain.agent_models import (
    CatalogFilters,
    CatalogInput,
    CatalogOutput,
)
from agentic_commerce_platform.domain.models import AgentResult
from agentic_commerce_platform.domain.ports import CatalogRepository, RetrievalPort
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider

__all__ = ["CatalogAgent"]

logger = logging.getLogger(__name__)


class CatalogAgent(BaseAgent):
    """Search the catalog structurally or via injected RAG retrieval.

    The agent never knows whether the repository is in-memory or SQL-backed. When
    a RetrievalService is injected and the query is non-empty, vector recall is
    attempted first and structured filters are applied by that service. Retrieval
    failure falls back to repository keyword search with an explicit warning.
    """

    def __init__(
        self,
        catalog_repository: CatalogRepository,
        llm_provider: LLMProvider,
        *,
        retrieval_service: RetrievalPort | None = None,
        name: str = "catalog_agent",
        timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize with repository, LLM, and optional retrieval dependency."""
        self._catalog_repository = catalog_repository
        self._llm_provider = llm_provider
        self._retrieval_service = retrieval_service
        super().__init__(name=name, timeout_seconds=timeout_seconds)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Search using RAG for non-empty queries or structured filters otherwise."""
        request = kwargs.get("request")
        if not isinstance(request, CatalogInput):
            raise ValueError("CatalogAgent requires a CatalogInput via 'request'")

        category = request.category.strip() if request.category else None
        warnings: list[str] = []
        retrieval_source: str | None = None
        retrieval_scores: dict[str, float] = {}
        retrieval_metadata: dict[str, Any] = {}
        products = []

        if request.query.strip() and self._retrieval_service is not None:
            try:
                retrieval = self._retrieval_service.search(
                    request.query,
                    category=category,
                    min_price=request.min_price,
                    max_price=request.max_price,
                    top_k=request.limit,
                )
                products = [candidate.product for candidate in retrieval.candidates]
                warnings.extend(retrieval.warnings)
                retrieval_source = retrieval.retrieval_source
                retrieval_scores = {
                    candidate.product.product_id: candidate.score
                    for candidate in retrieval.candidates
                }
                retrieval_metadata = {
                    "embedding_model": retrieval.embedding_model,
                    "top_k": request.limit,
                }
            except Exception:
                logger.exception("catalog_retrieval_fallback")
                warnings.append("retrieval_failed")
                products = self._catalog_repository.search(
                    query=request.query,
                    category=category,
                    min_price=request.min_price,
                    max_price=request.max_price,
                    active_only=True,
                )
                retrieval_source = "fallback"
                retrieval_metadata = {"fallback": "repository_keyword"}
        else:
            products = self._catalog_repository.search(
                query=request.query,
                category=category,
                min_price=request.min_price,
                max_price=request.max_price,
                active_only=True,
            )
            retrieval_source = self._catalog_repository.source.value

        matched_count = len(products)
        limited_products = products[: request.limit]
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
            retrieval_source=retrieval_source,
            retrieval_scores=retrieval_scores,
            retrieval_metadata=retrieval_metadata,
            warnings=warnings,
        )
        return AgentResult(
            agent_name=self.name,
            success=True,
            data=output.model_dump(mode="json"),
        )
