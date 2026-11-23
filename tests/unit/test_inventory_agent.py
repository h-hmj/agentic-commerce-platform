"""Tests for InventoryAgent sellability, alerts, and purchase limits."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentic_commerce_platform.agents.inventory_agent import InventoryAgent
from agentic_commerce_platform.domain.agent_models import InventoryInput, InventoryOutput
from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.infrastructure.data import InMemoryInventoryRepository
from agentic_commerce_platform.infrastructure.llm import MockLLMProvider
from tests.helpers import make_product, parse_output

_PRODUCTS = [
    make_product("p-1", stock=99),
    make_product("p-2", stock=99),
    make_product("p-3", stock=99),
    make_product("p-4", stock=99),
]


def _agent(stocks: dict[str, int] | None = None) -> InventoryAgent:
    return InventoryAgent(
        InMemoryInventoryRepository(stocks or {"p-1": 5, "p-2": 0, "p-3": 2}),
        MockLLMProvider(),
    )


async def test_available_unavailable_and_low_stock_rule() -> None:
    """Repository stock determines availability and low-stock alerts."""
    result = await _agent().run(
        request=InventoryInput(products=_PRODUCTS, low_stock_threshold=3)
    )
    output = parse_output(result, InventoryOutput)

    assert [product.product_id for product in output.available_products] == ["p-1", "p-3"]
    assert [product.product_id for product in output.unavailable_products] == ["p-2", "p-4"]
    assert output.unavailable_reasons["p-2"] == "out_of_stock"
    assert output.unavailable_reasons["p-4"] == "inventory_record_missing"
    assert output.source is DataSource.IN_MEMORY_DEMO
    assert output.available_products[0].stock == 5


async def test_low_stock_alert_and_purchase_limits() -> None:
    """Low stock produces an alert and a limit of at most two units."""
    output = parse_output(
        await _agent().run(
            request=InventoryInput(products=_PRODUCTS, low_stock_threshold=3)
        ),
        InventoryOutput,
    )

    alerts = {alert.product_id: alert for alert in output.low_stock_alerts}
    assert set(alerts) == {"p-3"}
    assert alerts["p-3"].stock == 2
    assert alerts["p-3"].threshold == 3
    assert output.purchase_limits == {"p-3": 2}
    assert "p-1" not in output.purchase_limits


async def test_stock_one_has_purchase_limit_one() -> None:
    """A single remaining unit can only have a purchase limit of one."""
    agent = _agent({"p-1": 1, "p-2": 0, "p-3": 0, "p-4": 0})

    output = parse_output(
        await agent.run(
            request=InventoryInput(products=_PRODUCTS[:1], low_stock_threshold=3)
        ),
        InventoryOutput,
    )

    assert output.purchase_limits == {"p-1": 1}
    assert output.low_stock_alerts[0].stock == 1


async def test_stock_equal_to_threshold_is_low_stock() -> None:
    """The threshold is inclusive."""
    agent = _agent({"p-1": 3, "p-2": 0, "p-3": 0, "p-4": 0})

    output = parse_output(
        await agent.run(
            request=InventoryInput(products=_PRODUCTS[:1], low_stock_threshold=3)
        ),
        InventoryOutput,
    )

    assert len(output.low_stock_alerts) == 1
    assert output.purchase_limits == {"p-1": 2}


async def test_empty_product_list() -> None:
    """An empty input is valid and returns empty decisions."""
    output = parse_output(
        await _agent().run(request=InventoryInput(products=[])),
        InventoryOutput,
    )

    assert output.available_products == []
    assert output.unavailable_products == []
    assert output.low_stock_alerts == []
    assert output.purchase_limits == {}


async def test_original_products_are_not_mutated() -> None:
    """Output stock resolution uses copies, preserving caller-owned products."""
    original_stock = _PRODUCTS[0].stock

    parse_output(
        await _agent().run(request=InventoryInput(products=_PRODUCTS)),
        InventoryOutput,
    )

    assert _PRODUCTS[0].stock == original_stock == 99


async def test_invalid_repository_stock_is_rejected() -> None:
    """Invalid stock values cause a structured failure, never a false success."""

    class InvalidStockRepository:
        @property
        def source(self) -> DataSource:
            return DataSource.IN_MEMORY_DEMO

        def get_stock(self, product_id: str) -> int | None:
            return -1

    agent = InventoryAgent(InvalidStockRepository(), MockLLMProvider())

    result = await agent.run(
        request=InventoryInput(products=[make_product("p-1")])
    )

    assert result.success is False
    assert result.error is not None
    assert "invalid inventory stock" in result.error


async def test_repository_failure_returns_structured_failure() -> None:
    """Stock lookup failures do not default to sufficient stock."""

    class BrokenRepository:
        @property
        def source(self) -> DataSource:
            return DataSource.IN_MEMORY_DEMO

        def get_stock(self, product_id: str) -> int | None:
            raise RuntimeError("inventory backend unavailable")

    agent = InventoryAgent(BrokenRepository(), MockLLMProvider())

    result = await agent.run(
        request=InventoryInput(products=[make_product("p-1")])
    )

    assert result.success is False
    assert result.error is not None
    assert "inventory backend unavailable" in result.error


@pytest.mark.parametrize("threshold", [-1, 101])
def test_invalid_low_stock_threshold(threshold: int) -> None:
    """The low-stock threshold is bounded by the input model."""
    with pytest.raises(ValidationError):
        InventoryInput(products=[], low_stock_threshold=threshold)
