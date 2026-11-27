"""Shared helpers for local vector stores."""

from __future__ import annotations

from agentic_commerce_platform.domain.models import Product

__all__ = ["product_text"]


def product_text(product: Product) -> str:
    """Build the indexable text from product fields, excluding inventory."""
    parts = [
        product.name,
        product.category,
        product.brand or "",
        product.description or "",
        " ".join(product.tags),
    ]
    return " | ".join(part.strip() for part in parts if part and part.strip())
