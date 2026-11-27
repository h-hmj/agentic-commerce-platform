"""SQLAlchemy catalog repository."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.domain.models import Product
from agentic_commerce_platform.infrastructure.database.models import (
    InventoryRecordORM,
    ProductORM,
)
from agentic_commerce_platform.infrastructure.database.session import DatabaseManager

__all__ = ["DatabaseCatalogRepository"]


class DatabaseCatalogRepository:
    """Catalog repository backed by SQLite/PostgreSQL/MySQL through SQLAlchemy."""

    def __init__(self, database: DatabaseManager) -> None:
        """Store the injected database manager."""
        self._database = database

    @property
    def source(self) -> DataSource:
        """Return database provenance."""
        return DataSource.DATABASE

    def search(
        self,
        *,
        query: str = "",
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        limit: int | None = None,
        active_only: bool = True,
    ) -> list[Product]:
        """Query products and their inventory stock from the database."""
        statement = select(ProductORM, InventoryRecordORM.stock).outerjoin(
            InventoryRecordORM,
            InventoryRecordORM.product_id == ProductORM.product_id,
        )
        if active_only:
            statement = statement.where(ProductORM.is_active.is_(True))
        if category:
            statement = statement.where(ProductORM.category == category)
        if min_price is not None:
            statement = statement.where(ProductORM.price >= min_price)
        if max_price is not None:
            statement = statement.where(ProductORM.price <= max_price)

        with self._database.session() as session:
            rows = session.execute(statement).all()

        tokens = query.strip().lower().split()
        products: list[Product] = []
        for product_row, stock in rows:
            searchable = " ".join(
                [
                    product_row.name,
                    product_row.category,
                    product_row.brand or "",
                    product_row.description or "",
                    *list(product_row.tags or []),
                ]
            ).lower()
            if tokens and not all(token in searchable for token in tokens):
                continue
            products.append(self._to_domain(product_row, stock))
        products.sort(key=lambda product: product.product_id)
        return products[:limit] if limit is not None else products

    def get_by_ids(self, product_ids: list[str]) -> list[Product]:
        """Return active products matching supplied IDs."""
        if not product_ids:
            return []
        statement = (
            select(ProductORM, InventoryRecordORM.stock)
            .outerjoin(
                InventoryRecordORM,
                InventoryRecordORM.product_id == ProductORM.product_id,
            )
            .where(
                ProductORM.is_active.is_(True),
                ProductORM.product_id.in_(product_ids),
            )
        )
        with self._database.session() as session:
            rows = session.execute(statement).all()
        products = [self._to_domain(row, stock) for row, stock in rows]
        products.sort(key=lambda product: product.product_id)
        return products

    @staticmethod
    def _to_domain(record: ProductORM, stock: int | None) -> Product:
        """Map ORM product plus inventory stock to the domain model."""
        return Product(
            product_id=record.product_id,
            name=record.name,
            category=record.category,
            description=record.description,
            brand=record.brand,
            is_active=record.is_active,
            price=record.price,
            stock=stock if stock is not None else 0,
            tags=list(record.tags or []),
        )
