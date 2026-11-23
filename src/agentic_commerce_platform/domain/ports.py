"""Ports implemented by phase-two data access adapters."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from agentic_commerce_platform.domain.agent_models import UserBehaviorRecord
from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.domain.models import Product

__all__ = ["CatalogRepository", "InventoryRepository", "UserBehaviorRepository"]


@runtime_checkable
class CatalogRepository(Protocol):
    """Read-only product catalog contract used by :class:`CatalogAgent`."""

    @property
    def source(self) -> DataSource:
        """Explicit provenance of returned products."""
        ...

    def search(
        self,
        *,
        query: str = "",
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
    ) -> list[Product]:
        """Return products matching all supplied filters."""
        ...


@runtime_checkable
class InventoryRepository(Protocol):
    """Read-only stock lookup contract used by :class:`InventoryAgent`."""

    @property
    def source(self) -> DataSource:
        """Explicit provenance of stock values."""
        ...

    def get_stock(self, product_id: str) -> int | None:
        """Return current stock, or ``None`` when no inventory record exists."""
        ...


@runtime_checkable
class UserBehaviorRepository(Protocol):
    """Read-only behavior contract used by :class:`UserProfileAgent`."""

    @property
    def source(self) -> DataSource:
        """Explicit provenance of behavior records."""
        ...

    def get_behavior(self, user_id: str) -> UserBehaviorRecord | None:
        """Return a copy of the behavior record, or ``None`` for unknown users."""
        ...
