"""Tests for the in-memory catalog adapter."""

from __future__ import annotations

from decimal import Decimal

import pytest

from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.infrastructure.data import InMemoryCatalogRepository
from tests.helpers import make_product


def _products():
    return [
        make_product("p-1", name="Python Book", category="books", price="100.00", tags=["python"]),
        make_product("p-2", name="Coffee Beans", category="grocery", price="80.00", tags=["coffee"]),
        make_product("p-3", name="Data Book", category="books", price="150.00", tags=["python", "data"]),
    ]


def test_catalog_search_filters_and_source() -> None:
    """Keyword, category, and price filters combine as AND conditions."""
    repository = InMemoryCatalogRepository(_products())

    results = repository.search(
        query="python",
        category="books",
        min_price=Decimal("120"),
        max_price=Decimal("200"),
    )

    assert [product.product_id for product in results] == ["p-3"]
    assert repository.source is DataSource.IN_MEMORY_DEMO


def test_catalog_returns_defensive_copies() -> None:
    """Callers cannot mutate repository state through returned products."""
    repository = InMemoryCatalogRepository(_products())
    first = repository.search(query="python")
    first[0].name = "mutated by caller"
    first[0].tags.append("injected")

    fresh = repository.search(query="python")

    assert fresh[0].name == "Python Book"
    assert "injected" not in fresh[0].tags


def test_catalog_rejects_duplicate_product_ids() -> None:
    """Duplicate seed IDs fail fast instead of creating ambiguous results."""
    duplicate = make_product("p-1", name="Duplicate")

    with pytest.raises(ValueError, match="unique product_id"):
        InMemoryCatalogRepository([_products()[0], duplicate])


def test_demo_catalog_is_loaded_without_custom_seed() -> None:
    """The default repository uses centralized phase-two demo data."""
    repository = InMemoryCatalogRepository()

    results = repository.search(query="python")

    assert results
    assert all(product.product_id for product in results)
    assert repository.source is DataSource.IN_MEMORY_DEMO
