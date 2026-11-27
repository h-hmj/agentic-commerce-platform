"""In-memory inventory adapter backed by phase-two demonstration data."""

from __future__ import annotations

from collections.abc import Mapping

from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.infrastructure.data.demo_data import DEMO_INVENTORY

__all__ = ["InMemoryInventoryRepository"]


class InMemoryInventoryRepository:
    """Deterministic, read-only inventory repository.

    The default stock mapping is phase-two in-memory demo data. Unknown product
    IDs return ``None`` so agents can treat them as unavailable rather than
    assuming sufficient stock.
    """

    def __init__(self, stocks: Mapping[str, int] | None = None) -> None:
        """Initialize the repository.

        Args:
            stocks: Optional deterministic stock mapping. Defaults to
                ``DEMO_INVENTORY``.

        Raises:
            ValueError: If a product ID is blank, a stock value is not a
                non-negative integer, or duplicate IDs are supplied.
        """
        source = dict(stocks) if stocks is not None else dict(DEMO_INVENTORY)
        validated: dict[str, int] = {}
        for product_id, stock in source.items():
            if not product_id.strip():
                raise ValueError("inventory product IDs must not be blank")
            if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
                raise ValueError(
                    f"inventory stock for {product_id!r} must be a non-negative integer"
                )
            if product_id in validated:
                raise ValueError(f"duplicate inventory product ID: {product_id!r}")
            validated[product_id] = stock
        self._stocks = validated

    @property
    def source(self) -> DataSource:
        """Return the explicit in-memory demo provenance marker."""
        return DataSource.IN_MEMORY_DEMO

    def get_stock(self, product_id: str) -> int | None:
        """Return the current stock for a product, or ``None`` if unknown."""
        return self._stocks.get(product_id)

    def get_stock_levels(self, product_ids: list[str]) -> dict[str, int | None]:
        """Return current stock values for a batch of products."""
        return {product_id: self._stocks.get(product_id) for product_id in product_ids}

    def update_stock(self, product_id: str, stock: int) -> int:
        """Update in-memory stock after validating a non-negative integer."""
        if not product_id.strip():
            raise ValueError("inventory product IDs must not be blank")
        if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
            raise ValueError("inventory stock must be a non-negative integer")
        self._stocks[product_id] = stock
        return stock
