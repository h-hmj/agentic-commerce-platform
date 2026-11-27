"""Local vector stores: in-process and SQLite-backed cosine search."""

from __future__ import annotations

import math

from sqlalchemy import select

from agentic_commerce_platform.domain.data_models import VectorHit, VectorRecord
from agentic_commerce_platform.infrastructure.database.models import ProductEmbeddingORM
from agentic_commerce_platform.infrastructure.database.session import DatabaseManager

__all__ = ["InMemoryVectorStore", "SQLiteVectorStore", "cosine_similarity"]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity clamped to the public [0, 1] range."""
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


class InMemoryVectorStore:
    """Process-local deterministic vector index for offline mode and tests."""

    def __init__(self) -> None:
        """Create an empty index."""
        self._records: dict[str, VectorRecord] = {}

    def upsert(self, record: VectorRecord) -> None:
        """Insert or replace a vector record."""
        self._records[record.product_id] = record.model_copy(deep=True)

    def search(
        self,
        vector: list[float],
        *,
        top_k: int,
        score_threshold: float,
    ) -> list[VectorHit]:
        """Return hits above threshold, ordered by descending similarity."""
        hits = [
            VectorHit(
                product_id=record.product_id,
                score=cosine_similarity(vector, record.vector),
                embedding_model=record.embedding_model,
            )
            for record in self._records.values()
        ]
        hits = [hit for hit in hits if hit.score >= score_threshold]
        hits.sort(key=lambda hit: (-hit.score, hit.product_id))
        return hits[:top_k]

    def delete(self, product_id: str) -> None:
        """Remove a vector if present."""
        self._records.pop(product_id, None)

    def count(self) -> int:
        """Return the number of indexed products."""
        return len(self._records)


class SQLiteVectorStore:
    """Persistent local vector store using the product_embeddings SQL table.

    Similarity is computed in Python because the dataset is intentionally local
    and small. This is not a replacement for a production vector database.
    """

    def __init__(self, database: DatabaseManager, *, collection: str) -> None:
        """Store the injected database and collection name."""
        if not collection.strip():
            raise ValueError("collection must not be blank")
        self._database = database
        self._collection = collection

    def upsert(self, record: VectorRecord) -> None:
        """Insert or update a persisted vector record."""
        with self._database.session() as session:
            existing = session.scalar(
                select(ProductEmbeddingORM).where(
                    ProductEmbeddingORM.product_id == record.product_id
                )
            )
            if existing is None:
                existing = ProductEmbeddingORM(
                    product_id=record.product_id,
                    collection=self._collection,
                )
                session.add(existing)
            existing.text = record.text
            existing.vector = list(record.vector)
            existing.embedding_model = record.embedding_model
            existing.collection = self._collection
            session.flush()

    def search(
        self,
        vector: list[float],
        *,
        top_k: int,
        score_threshold: float,
    ) -> list[VectorHit]:
        """Search all persisted vectors with deterministic cosine similarity."""
        with self._database.session() as session:
            records = session.scalars(
                select(ProductEmbeddingORM).where(
                    ProductEmbeddingORM.collection == self._collection
                )
            ).all()
        hits = [
            VectorHit(
                product_id=record.product_id,
                score=cosine_similarity(vector, list(record.vector)),
                embedding_model=record.embedding_model,
            )
            for record in records
        ]
        hits = [hit for hit in hits if hit.score >= score_threshold]
        hits.sort(key=lambda hit: (-hit.score, hit.product_id))
        return hits[:top_k]

    def delete(self, product_id: str) -> None:
        """Delete a persisted product vector."""
        with self._database.session() as session:
            record = session.scalar(
                select(ProductEmbeddingORM).where(
                    ProductEmbeddingORM.product_id == product_id
                )
            )
            if record is not None:
                session.delete(record)

    def count(self) -> int:
        """Return the number of persisted vectors in this collection."""
        with self._database.session() as session:
            return len(
                session.scalars(
                    select(ProductEmbeddingORM.id).where(
                        ProductEmbeddingORM.collection == self._collection
                    )
                ).all()
            )
