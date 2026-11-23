"""Inventory decision agent using an injected stock repository."""

from __future__ import annotations

from typing import Any

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.domain.agent_models import (
    InventoryInput,
    InventoryOutput,
    LowStockAlert,
)
from agentic_commerce_platform.domain.models import AgentResult, Product
from agentic_commerce_platform.domain.ports import InventoryRepository
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider

__all__ = ["InventoryAgent"]


class InventoryAgent(BaseAgent):
    """Evaluate sellability, low-stock alerts, and purchase limits.

    Current stock comes exclusively from the injected repository. Missing stock
    records are treated as unavailable; invalid stock values are rejected rather
    than assumed sufficient. Input products are copied and never mutated.
    """

    def __init__(
        self,
        inventory_repository: InventoryRepository,
        llm_provider: LLMProvider,
        *,
        name: str = "inventory_agent",
        timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize the agent with injected inventory and LLM dependencies."""
        self._inventory_repository = inventory_repository
        self._llm_provider = llm_provider
        super().__init__(name=name, timeout_seconds=timeout_seconds)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Evaluate inventory for an :class:`InventoryInput` request."""
        request = kwargs.get("request")
        if not isinstance(request, InventoryInput):
            raise ValueError("InventoryAgent requires an InventoryInput via 'request'")

        available: list[Product] = []
        unavailable: list[Product] = []
        alerts: list[LowStockAlert] = []
        purchase_limits: dict[str, int] = {}
        unavailable_reasons: dict[str, str] = {}
        seen_ids: set[str] = set()

        for product in request.products:
            if product.product_id in seen_ids:
                continue
            seen_ids.add(product.product_id)

            stock = self._inventory_repository.get_stock(product.product_id)
            if stock is None:
                unavailable.append(product.model_copy(deep=True))
                unavailable_reasons[product.product_id] = "inventory_record_missing"
                continue
            if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
                raise ValueError(
                    f"invalid inventory stock for {product.product_id!r}: {stock!r}"
                )

            resolved_product = product.model_copy(
                deep=True,
                update={"stock": stock},
            )
            if stock <= 0:
                unavailable.append(resolved_product)
                unavailable_reasons[product.product_id] = "out_of_stock"
                continue

            available.append(resolved_product)
            if 1 <= stock <= request.low_stock_threshold:
                alerts.append(
                    LowStockAlert(
                        product_id=product.product_id,
                        product_name=product.name,
                        stock=stock,
                        threshold=request.low_stock_threshold,
                        message=(
                            f"{product.name} is low on stock: {stock} remaining "
                            f"(threshold {request.low_stock_threshold})."
                        ),
                    )
                )
                purchase_limits[product.product_id] = min(stock, 2)

        output = InventoryOutput(
            available_products=available,
            unavailable_products=unavailable,
            low_stock_alerts=alerts,
            purchase_limits=purchase_limits,
            unavailable_reasons=unavailable_reasons,
            source=self._inventory_repository.source,
        )
        return AgentResult(
            agent_name=self.name,
            success=True,
            data=output.model_dump(mode="json"),
        )
