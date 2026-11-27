"""SQLAlchemy inventory repository."""

from __future__ import annotations

from sqlalchemy import select

from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.infrastructure.database.models import InventoryRecordORM
from agentic_commerce_platform.infrastructure.database.session import DatabaseManager

__all__ = ["DatabaseInventoryRepository"]


class DatabaseInventoryRepository:
    """Inventory repository; database stock is the authoritative source."""

    def __init__(self, database: DatabaseManager) -> None:
        """Store the injected database manager."""
        self._database = database

    @property
    def source(self) -> DataSource:
        """Return database provenance."""
        return DataSource.DATABASE

    def get_stock(self, product_id: str) -> int | None:
        """Return stock or ``None`` when no inventory record exists."""
        with self._database.session() as session:
            stock = session.scalar(
                select(InventoryRecordORM.stock).where(
                    InventoryRecordORM.product_id == product_id
                )
            )
        return stock

    def get_stock_levels(self, product_ids: list[str]) -> dict[str, int | None]:
        """Return batch stock values without assuming missing records are in stock."""
        if not product_ids:
            return {}
        with self._database.session() as session:
            rows = session.execute(
                select(InventoryRecordORM.product_id, InventoryRecordORM.stock).where(
                    InventoryRecordORM.product_id.in_(product_ids)
                )
            ).all()
        found = {product_id: stock for product_id, stock in rows}
        return {product_id: found.get(product_id) for product_id in product_ids}

    def update_stock(self, product_id: str, stock: int) -> int:
        """Update stock, creating a record if missing; negative values are rejected."""
        if not product_id.strip():
            raise ValueError("inventory product IDs must not be blank")
        if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
            raise ValueError("inventory stock must be a non-negative integer")
        with self._database.session() as session:
            record = session.scalar(
                select(InventoryRecordORM).where(
                    InventoryRecordORM.product_id == product_id
                )
            )
            if record is None:
                record = InventoryRecordORM(
                    product_id=product_id,
                    stock=stock,
                    reserved_stock=0,
                )
                session.add(record)
            else:
                record.stock = stock
            session.flush()
        return stock
