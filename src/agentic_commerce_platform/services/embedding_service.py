"""Indexing service for product embeddings."""

from __future__ import annotations

import logging

from agentic_commerce_platform.domain.data_models import VectorRecord
from agentic_commerce_platform.domain.models import Product
from agentic_commerce_platform.domain.ports import EmbeddingProvider, VectorStore
from agentic_commerce_platform.infrastructure.vector_store.base import product_text

__all__ = ["EmbeddingService"]

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Build and persist deterministic product embeddings locally."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> None:
        """Inject embedding and vector-store ports."""
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store

    @property
    def model_name(self) -> str:
        """Return the configured embedding model identifier."""
        return self._embedding_provider.model_name

    def index_products(self, products: list[Product]) -> int:
        """Embed and upsert active products, returning the indexed count."""
        indexed = 0
        for product in products:
            if not product.is_active:
                self._vector_store.delete(product.product_id)
                continue
            text = product_text(product)
            if not text.strip():
                continue
            vector = self._embedding_provider.embed_text(text)
            self._vector_store.upsert(
                VectorRecord(
                    product_id=product.product_id,
                    text=text,
                    vector=vector,
                    embedding_model=self._embedding_provider.model_name,
                    payload={
                        "name": product.name,
                        "category": product.category,
                        "brand": product.brand,
                    },
                )
            )
            indexed += 1
        logger.info("embeddings_indexed", extra={"final_product_count": indexed})
        return indexed

    def embed_query(self, query: str) -> list[float]:
        """Embed a non-empty query using the same provider as documents."""
        return self._embedding_provider.embed_text(query)
