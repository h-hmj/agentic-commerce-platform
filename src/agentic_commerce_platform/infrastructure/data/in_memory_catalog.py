"""In-memory catalog adapter backed by phase-two demonstration data."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.domain.models import Product
from agentic_commerce_platform.infrastructure.data.demo_data import DEMO_PRODUCTS

__all__ = ["InMemoryCatalogRepository"]


class InMemoryCatalogRepository:
    """Deterministic, read-only catalog repository.

    The adapter owns copies of the supplied products and returns deep copies on
    every read, so callers cannot mutate the repository's internal state. The
    default dataset is phase-two in-memory demo data, never a real catalog.
    """

    def __init__(self, products: Sequence[Product] | None = None) -> None:
        """Initialize the repository.

        Args:
            products: Optional deterministic seed data. Defaults to
                ``DEMO_PRODUCTS``, which is explicitly demonstration data.

        Raises:
            ValueError: If product IDs are duplicated or empty.
        """
        source_products = list(products) if products is not None else list(DEMO_PRODUCTS)
        product_ids = [product.product_id for product in source_products]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("catalog products must have unique product_id values")
        self._products = tuple(product.model_copy(deep=True) for product in source_products)

    @property
    def source(self) -> DataSource:
        """Return the explicit in-memory demo provenance marker."""
        return DataSource.IN_MEMORY_DEMO

    def search(
        self,
        *,
        query: str = "",
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
    ) -> list[Product]:
        """Return products matching every supplied filter.

        Keyword matching is case-insensitive. All whitespace-separated query
        tokens must occur in the product name, category, or tags. Category and
        price bounds are inclusive.

        Args:
            query: Optional keyword query.
            category: Optional category filter.
            min_price: Optional inclusive minimum price.
            max_price: Optional inclusive maximum price.

        Returns:
            Deep copies of matching products sorted by ``product_id``.
        """
        normalized_query = query.strip().lower()
        tokens = normalized_query.split()
        normalized_category = category.strip().lower() if category else None

        matches: list[Product] = []
        for product in self._products:
            searchable = " ".join(
                [product.name, product.category, *product.tags]
            ).lower()
            if tokens and not all(token in searchable for token in tokens):
                continue
            if normalized_category and product.category.lower() != normalized_category:
                continue
            if min_price is not None and product.price < min_price:
                continue
            if max_price is not None and product.price > max_price:
                continue
            matches.append(product)

        matches.sort(key=lambda product: product.product_id)
        return [product.model_copy(deep=True) for product in matches]
