"""RAG candidate retrieval: vector recall plus explicit rule filtering."""

from __future__ import annotations

import logging
from decimal import Decimal

from agentic_commerce_platform.domain.data_models import (
    RetrievalResult,
    RetrievedCandidate,
)
from agentic_commerce_platform.domain.enums import DataSource, RetrievalSource
from agentic_commerce_platform.domain.ports import (
    CatalogRepository,
    EmbeddingProvider,
    InventoryRepository,
    VectorStore,
)

__all__ = ["RetrievalService"]

logger = logging.getLogger(__name__)


class RetrievalService:
    """Combine semantic recall with catalog, active, price, and stock filters.

    Vector similarity is a recall signal only. It is never the final ranking
    score; RecommendationAgent still owns final ordering.
    """

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        catalog_repository: CatalogRepository,
        inventory_repository: InventoryRepository | None = None,
        top_k: int = 8,
        score_threshold: float = 0.05,
    ) -> None:
        """Inject retrieval dependencies and local defaults."""
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._catalog_repository = catalog_repository
        self._inventory_repository = inventory_repository
        self._top_k = top_k
        self._score_threshold = score_threshold

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        top_k: int | None = None,
        include_out_of_stock: bool = False,
    ) -> RetrievalResult:
        """Return traceable candidates, falling back to keyword search on failure."""
        normalized_query = query.strip()
        effective_top_k = max(1, min(50, top_k or self._top_k))
        if not normalized_query:
            return self._keyword_result(
                normalized_query,
                category=category,
                min_price=min_price,
                max_price=max_price,
                limit=effective_top_k,
                warnings=[],
                source=self._keyword_source(),
            )

        warnings: list[str] = []
        try:
            query_vector = self._embedding_provider.embed_text(normalized_query)
        except Exception:
            logger.exception("embedding_failed")
            warnings.append("embedding_failed")
            return self._keyword_result(
                normalized_query,
                category=category,
                min_price=min_price,
                max_price=max_price,
                limit=effective_top_k,
                warnings=warnings,
                source=RetrievalSource.FALLBACK,
            )

        try:
            hits = self._vector_store.search(
                query_vector,
                top_k=effective_top_k * 2,
                score_threshold=self._score_threshold,
            )
        except Exception:
            logger.exception("vector_search_failed")
            warnings.append("vector_retrieval_failed")
            return self._keyword_result(
                normalized_query,
                category=category,
                min_price=min_price,
                max_price=max_price,
                limit=effective_top_k,
                warnings=warnings,
                source=RetrievalSource.FALLBACK,
            )

        if not hits:
            return RetrievalResult(
                query=normalized_query,
                candidates=[],
                retrieval_source=RetrievalSource.VECTOR.value,
                warnings=warnings,
                embedding_model=self._embedding_provider.model_name,
            )

        products = {
            product.product_id: product
            for product in self._catalog_repository.get_by_ids(
                [hit.product_id for hit in hits]
            )
        }
        stock_levels = (
            self._inventory_repository.get_stock_levels(list(products))
            if self._inventory_repository is not None
            else {}
        )
        candidates: list[RetrievedCandidate] = []
        seen: set[str] = set()
        for hit in hits:
            product = products.get(hit.product_id)
            if product is None or not product.is_active or product.product_id in seen:
                continue
            if category and product.category.lower() != category.lower():
                continue
            if min_price is not None and product.price < min_price:
                continue
            if max_price is not None and product.price > max_price:
                continue
            if not include_out_of_stock and self._inventory_repository is not None:
                stock = stock_levels.get(product.product_id)
                if stock is None or stock <= 0:
                    continue
                product = product.model_copy(update={"stock": stock})
            seen.add(product.product_id)
            candidates.append(
                RetrievedCandidate(
                    product=product,
                    score=hit.score,
                    source=RetrievalSource.VECTOR,
                    retrieval_query=normalized_query,
                    matched_fields=["vector"],
                    embedding_model=hit.embedding_model
                    or self._embedding_provider.model_name,
                )
            )
            if len(candidates) >= effective_top_k:
                break

        return RetrievalResult(
            query=normalized_query,
            candidates=candidates,
            retrieval_source=RetrievalSource.VECTOR.value,
            warnings=warnings,
            embedding_model=self._embedding_provider.model_name,
        )

    def _keyword_source(self) -> RetrievalSource:
        """Return an honest keyword source for the configured catalog adapter."""
        if self._catalog_repository.source in {
            DataSource.IN_MEMORY,
            DataSource.IN_MEMORY_DEMO,
        }:
            return RetrievalSource.IN_MEMORY
        return RetrievalSource.DATABASE_KEYWORD

    def _keyword_result(
        self,
        query: str,
        *,
        category: str | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        limit: int,
        warnings: list[str],
        source: RetrievalSource,
    ) -> RetrievalResult:
        """Fallback to structured catalog search with explicit source."""
        products = self._catalog_repository.search(
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            limit=limit,
            active_only=True,
        )
        candidates = [
            RetrievedCandidate(
                product=product,
                score=0.0,
                source=source,
                retrieval_query=query,
                matched_fields=["keyword"],
                embedding_model=None,
            )
            for product in products
        ]
        return RetrievalResult(
            query=query,
            candidates=candidates,
            retrieval_source=source.value,
            warnings=warnings,
            embedding_model=None,
        )
