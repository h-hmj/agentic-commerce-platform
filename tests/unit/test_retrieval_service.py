"""RAG retrieval tests: vector recall, filters, provenance, and fallback."""

from __future__ import annotations

from decimal import Decimal

from agentic_commerce_platform.domain.models import Product
from agentic_commerce_platform.infrastructure.data import (
    InMemoryCatalogRepository,
    InMemoryInventoryRepository,
)
from agentic_commerce_platform.infrastructure.vector_store import (
    DeterministicEmbeddingProvider,
    InMemoryVectorStore,
)
from agentic_commerce_platform.services.embedding_service import EmbeddingService
from agentic_commerce_platform.services.retrieval_service import RetrievalService
from tests.helpers import make_product


def _products() -> list[Product]:
    return [
        make_product("p-1", name="Python 编程实战", category="books", price="89.00"),
        make_product("p-2", name="数据科学入门", category="books", price="129.00"),
        make_product("p-3", name="咖啡豆礼盒", category="grocery", price="59.00"),
        make_product(
            "p-4",
            name="已下架 Python 旧书",
            category="books",
            price="39.00",
            stock=3,
        ).model_copy(update={"is_active": False}),
    ]


def _retrieval_service(
    *,
    catalog: InMemoryCatalogRepository,
    inventory: InMemoryInventoryRepository,
    vector_store=None,
    embedding=None,
) -> RetrievalService:
    provider = embedding or DeterministicEmbeddingProvider(dimensions=32)
    store = vector_store or InMemoryVectorStore()
    return RetrievalService(
        embedding_provider=provider,
        vector_store=store,
        catalog_repository=catalog,
        inventory_repository=inventory,
        top_k=3,
        score_threshold=0.0,
    )


def test_vector_retrieval_returns_traceable_scores() -> None:
    """Semantic candidates include score, source, query, and model."""
    catalog = InMemoryCatalogRepository(_products())
    inventory = InMemoryInventoryRepository({"p-1": 5, "p-2": 4, "p-3": 8})
    embedding = DeterministicEmbeddingProvider(dimensions=32)
    store = InMemoryVectorStore()
    EmbeddingService(embedding, store).index_products(catalog.search())
    service = _retrieval_service(
        catalog=catalog,
        inventory=inventory,
        vector_store=store,
        embedding=embedding,
    )

    result = service.search("Python 编程", category="books", top_k=2)

    assert result.retrieval_source == "vector"
    assert result.candidates
    assert all(candidate.score >= 0 for candidate in result.candidates)
    assert all(candidate.source.value == "vector" for candidate in result.candidates)
    assert all(candidate.embedding_model for candidate in result.candidates)
    assert all(candidate.product.category == "books" for candidate in result.candidates)


def test_retrieval_applies_price_and_inventory_filters() -> None:
    """Structured filters are applied after vector recall."""
    catalog = InMemoryCatalogRepository(_products())
    inventory = InMemoryInventoryRepository({"p-1": 5, "p-2": 0, "p-3": 8})
    embedding = DeterministicEmbeddingProvider(dimensions=32)
    store = InMemoryVectorStore()
    EmbeddingService(embedding, store).index_products(catalog.search())
    service = _retrieval_service(
        catalog=catalog,
        inventory=inventory,
        vector_store=store,
        embedding=embedding,
    )

    result = service.search(
        "Python",
        min_price=Decimal("50"),
        max_price=Decimal("100"),
        top_k=3,
    )

    assert all(candidate.product.price <= Decimal("100") for candidate in result.candidates)
    assert all(candidate.product.stock > 0 for candidate in result.candidates)
    assert all(candidate.product.product_id != "p-2" for candidate in result.candidates)
    assert all(candidate.product.is_active for candidate in result.candidates)


class BrokenVectorStore:
    """Vector store that always raises so fallback behavior can be tested."""

    def upsert(self, record) -> None:
        raise RuntimeError("vector unavailable")

    def search(self, vector, *, top_k, score_threshold):
        raise RuntimeError("vector unavailable")

    def delete(self, product_id: str) -> None:
        return None

    def count(self) -> int:
        return 0


class BrokenEmbeddingProvider:
    """Embedding provider used to test keyword fallback."""

    model_name = "broken"

    def embed_text(self, text: str) -> list[float]:
        raise RuntimeError("embedding unavailable")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding unavailable")


def test_vector_failure_degrades_to_keyword_with_warning() -> None:
    """Vector failure returns explicit fallback provenance, not silent success."""
    catalog = InMemoryCatalogRepository(_products())
    service = _retrieval_service(
        catalog=catalog,
        inventory=InMemoryInventoryRepository({"p-1": 5}),
        vector_store=BrokenVectorStore(),
    )

    result = service.search("Python")

    assert result.retrieval_source == "fallback"
    assert "vector_retrieval_failed" in result.warnings
    assert result.candidates
    assert result.candidates[0].source.value == "fallback"


def test_embedding_failure_degrades_to_keyword() -> None:
    """Embedding failure does not fabricate vectors."""
    catalog = InMemoryCatalogRepository(_products())
    service = _retrieval_service(
        catalog=catalog,
        inventory=InMemoryInventoryRepository({"p-1": 5}),
        embedding=BrokenEmbeddingProvider(),  # type: ignore[arg-type]
    )

    result = service.search("Python")

    assert result.retrieval_source == "fallback"
    assert "embedding_failed" in result.warnings
    assert result.candidates


def test_empty_query_uses_keyword_source() -> None:
    """An empty semantic query falls back to structured catalog search."""
    catalog = InMemoryCatalogRepository(_products())
    service = _retrieval_service(
        catalog=catalog,
        inventory=InMemoryInventoryRepository({"p-1": 5, "p-2": 5, "p-3": 5}),
    )

    result = service.search("", category="books", top_k=3)

    assert result.query == ""
    assert result.retrieval_source in {"in_memory", "database_keyword"}
    assert result.candidates
