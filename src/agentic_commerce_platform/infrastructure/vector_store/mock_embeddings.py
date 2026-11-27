"""Deterministic offline embeddings for local development and tests."""

from __future__ import annotations

import hashlib
import math
import re

__all__ = ["DeterministicEmbeddingProvider"]

_TOKEN_PATTERN = re.compile(r"[\w\-]+", re.UNICODE)


class DeterministicEmbeddingProvider:
    """Hashing-based deterministic embedding provider.

    This is deliberately not a semantic neural model. It provides stable,
    reproducible vectors for local RAG wiring and tests, and must not be
    described as a real production embedding model.
    """

    def __init__(self, *, dimensions: int = 64, model_name: str = "deterministic-hash-v1") -> None:
        """Configure dimensions and a stable model identifier."""
        if dimensions < 8 or dimensions > 1024:
            raise ValueError("dimensions must be between 8 and 1024")
        if not model_name.strip():
            raise ValueError("model_name must not be blank")
        self._dimensions = dimensions
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        """Return the deterministic model identifier."""
        return self._model_name

    def embed_text(self, text: str) -> list[float]:
        """Return a normalized deterministic hash vector for non-empty text."""
        normalized = text.strip().lower()
        if not normalized:
            raise ValueError("text must not be blank")
        vector = [0.0] * self._dimensions
        for token in _TOKEN_PATTERN.findall(normalized):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return [1.0] + [0.0] * (self._dimensions - 1)
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch in order; an empty batch is valid."""
        return [self.embed_text(text) for text in texts]
