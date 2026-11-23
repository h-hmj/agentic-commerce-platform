"""Tests for CatalogAgent filtering, limits, and repository isolation."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from agentic_commerce_platform.agents.catalog_agent import CatalogAgent
from agentic_commerce_platform.domain.agent_models import CatalogInput, CatalogOutput
from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.infrastructure.data import InMemoryCatalogRepository
from agentic_commerce_platform.infrastructure.llm import MockLLMProvider
from tests.helpers import make_product, parse_output

_PRODUCTS = [
    make_product("p-1", name="Python Book", category="books", price="100.00", tags=["python"]),
    make_product("p-2", name="Data Book", category="books", price="150.00", tags=["python", "data"]),
    make_product("p-3", name="Coffee Beans", category="grocery", price="80.00", tags=["coffee"]),
    make_product("p-4", name="Premium Watch", category="electronics", price="300.00", tags=["premium"]),
]


def _agent() -> CatalogAgent:
    return CatalogAgent(
        InMemoryCatalogRepository(_PRODUCTS),
        MockLLMProvider(),
    )


async def test_keyword_search() -> None:
    """Keyword matching searches name, category, and tags."""
    result = await _agent().run(request=CatalogInput(query="python"))
    output = parse_output(result, CatalogOutput)

    assert [product.product_id for product in output.products] == ["p-1", "p-2"]
    assert output.matched_count == 2
    assert output.source is DataSource.IN_MEMORY_DEMO


async def test_category_filter() -> None:
    """Category filtering is exact and case-insensitive."""
    result = await _agent().run(request=CatalogInput(category="BOOKS"))
    output = parse_output(result, CatalogOutput)

    assert [product.product_id for product in output.products] == ["p-1", "p-2"]


async def test_minimum_and_maximum_price_filter() -> None:
    """Price bounds are inclusive."""
    result = await _agent().run(
        request=CatalogInput(
            min_price=Decimal("100.00"),
            max_price=Decimal("150.00"),
        )
    )
    output = parse_output(result, CatalogOutput)

    assert [product.product_id for product in output.products] == ["p-1", "p-2"]


async def test_combined_filters() -> None:
    """All query, category, and price filters combine with AND semantics."""
    result = await _agent().run(
        request=CatalogInput(
            query="python",
            category="books",
            min_price=Decimal("120.00"),
        )
    )
    output = parse_output(result, CatalogOutput)

    assert [product.product_id for product in output.products] == ["p-2"]
    assert output.filters.category == "books"
    assert output.filters.min_price == Decimal("120.00")


async def test_limit_does_not_change_matched_count() -> None:
    """``limit`` caps returned products while matched_count reports all matches."""
    result = await _agent().run(request=CatalogInput(limit=2))
    output = parse_output(result, CatalogOutput)

    assert len(output.products) == 2
    assert output.matched_count == 4


async def test_no_results_returns_empty_output() -> None:
    """No matches produce empty products and matched_count zero."""
    result = await _agent().run(request=CatalogInput(query="does-not-exist"))
    output = parse_output(result, CatalogOutput)

    assert output.products == []
    assert output.matched_count == 0
    assert output.source is DataSource.IN_MEMORY_DEMO


async def test_empty_query_returns_all_up_to_limit() -> None:
    """An empty query is valid and means no keyword constraint."""
    result = await _agent().run(request=CatalogInput(query="", limit=3))
    output = parse_output(result, CatalogOutput)

    assert len(output.products) == 3
    assert output.matched_count == 4
    assert output.query == ""


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_price": Decimal("20"), "max_price": Decimal("10")},
        {"limit": 0},
        {"limit": 51},
        {"category": "   "},
    ],
)
def test_invalid_catalog_input_is_rejected(kwargs: dict[str, object]) -> None:
    """Invalid price ranges and limits fail before repository access."""
    with pytest.raises(ValidationError):
        CatalogInput(**kwargs)


async def test_repository_results_are_copies() -> None:
    """A caller cannot mutate the repository through the agent output."""
    repository = InMemoryCatalogRepository(_PRODUCTS)
    agent = CatalogAgent(repository, MockLLMProvider())
    output = parse_output(
        await agent.run(request=CatalogInput(query="python")),
        CatalogOutput,
    )

    output.products[0].name = "mutated"
    fresh = repository.search(query="python")

    assert fresh[0].name == "Python Book"
