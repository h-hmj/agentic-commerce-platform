"""Local vector stores and deterministic embedding providers."""

from agentic_commerce_platform.infrastructure.vector_store.base import product_text
from agentic_commerce_platform.infrastructure.vector_store.local_vector_store import (
    InMemoryVectorStore,
    SQLiteVectorStore,
    cosine_similarity,
)
from agentic_commerce_platform.infrastructure.vector_store.mock_embeddings import (
    DeterministicEmbeddingProvider,
)

__all__ = [
    "DeterministicEmbeddingProvider",
    "InMemoryVectorStore",
    "SQLiteVectorStore",
    "cosine_similarity",
    "product_text",
]
