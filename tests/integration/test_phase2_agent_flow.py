"""Independent phase-two agent/service integration tests.

The services are invoked separately with externally supplied inputs. No
Supervisor, graph, agent-to-agent calls, network, database, or API key is used.
"""

from __future__ import annotations

import socket
from decimal import Decimal

import pytest

from agentic_commerce_platform.domain.agent_models import (
    CatalogInput,
    InventoryInput,
    MarketingInput,
    RecommendationInput,
    UserProfileInput,
)
from agentic_commerce_platform.domain.enums import (
    DataSource,
    MarketingProvider,
    RecommendationStrategy,
    UserSegment,
)
from agentic_commerce_platform.domain.errors import AgentExecutionError
from agentic_commerce_platform.infrastructure.data import (
    InMemoryCatalogRepository,
    InMemoryInventoryRepository,
    InMemoryUserBehaviorRepository,
)
from agentic_commerce_platform.infrastructure.llm import MockLLMProvider
from agentic_commerce_platform.services import (
    CatalogService,
    InventoryService,
    MarketingService,
    ProductRecommendationService,
    ProfileService,
)
from tests.helpers import make_product, make_profile


async def test_all_phase2_services_run_independently_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each service runs alone through injected dependencies, fully offline."""

    def block_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("outbound network access attempted")

    monkeypatch.setattr(socket, "create_connection", block_network)

    provider = MockLLMProvider()
    profile_service = ProfileService(InMemoryUserBehaviorRepository(), provider)
    catalog_service = CatalogService(InMemoryCatalogRepository(), provider)
    recommendation_service = ProductRecommendationService(provider)
    inventory_service = InventoryService(InMemoryInventoryRepository(), provider)
    marketing_service = MarketingService(provider)

    static_profile = make_profile(
        segments=[UserSegment.ACTIVE, UserSegment.HIGH_VALUE],
        preferred_categories=["books"],
        min_price="0.00",
        max_price="200.00",
        recent_interests=["python"],
    )
    static_products = [
        make_product("x-1", name="Python Book", category="books", price="99.00"),
        make_product("x-2", name="Coffee Beans", category="grocery", price="80.00"),
    ]

    profile = await profile_service.build_profile(
        UserProfileInput(user_id="u-demo-001")
    )
    catalog = await catalog_service.search_products(
        CatalogInput(query="python", limit=5)
    )
    recommendation = await recommendation_service.recommend_products(
        RecommendationInput(
            user_profile=static_profile,
            candidate_products=static_products,
            num_items=2,
        )
    )
    inventory = await inventory_service.evaluate_inventory(
        InventoryInput(products=static_products, low_stock_threshold=3)
    )
    marketing = await marketing_service.generate_copies(
        MarketingInput(user_profile=static_profile, products=static_products)
    )

    assert profile.data_source is DataSource.IN_MEMORY_DEMO
    assert catalog.source is DataSource.IN_MEMORY_DEMO
    assert catalog.matched_count >= 1
    assert recommendation.strategy is RecommendationStrategy.RULE_BASED_DEMO
    assert recommendation.products
    assert inventory.source is DataSource.IN_MEMORY_DEMO
    assert len(marketing.copies) == 2
    assert all(
        copy.provider in {MarketingProvider.MOCK, MarketingProvider.RULE_BASED}
        for copy in marketing.copies
    )


async def test_services_work_without_api_key_or_external_configuration() -> None:
    """No API key, Redis, database, or vector store is required."""
    provider = MockLLMProvider()
    profile_service = ProfileService(InMemoryUserBehaviorRepository(), provider)
    catalog_service = CatalogService(InMemoryCatalogRepository(), provider)

    profile = await profile_service.build_profile(
        UserProfileInput(user_id="u-demo-004")
    )
    catalog = await catalog_service.search_products(CatalogInput(limit=1))

    assert UserSegment.NEW_USER in profile.segments
    assert profile.confidence >= 0.0
    assert catalog.products


async def test_service_translates_agent_failure() -> None:
    """A broken repository becomes a project-level AgentExecutionError."""

    class BrokenInventoryRepository:
        @property
        def source(self) -> DataSource:
            return DataSource.IN_MEMORY_DEMO

        def get_stock(self, product_id: str) -> int | None:
            raise RuntimeError("inventory unavailable")

    service = InventoryService(BrokenInventoryRepository(), MockLLMProvider())

    with pytest.raises(AgentExecutionError) as exc_info:
        await service.evaluate_inventory(
            InventoryInput(products=[make_product("p-1")])
        )

    assert exc_info.value.agent_name == "inventory_agent"
    assert "inventory unavailable" in (exc_info.value.details["agent_error"] or "")


async def test_recommendation_service_accepts_external_profile_and_products() -> None:
    """Ranking remains independently callable with caller-supplied data."""
    profile = make_profile(
        segments=[UserSegment.PRICE_SENSITIVE],
        preferred_categories=["books"],
        min_price="0.00",
        max_price="150.00",
        recent_interests=["python"],
    )
    service = ProductRecommendationService(MockLLMProvider())

    output = await service.recommend_products(
        RecommendationInput(
            user_profile=profile,
            candidate_products=[
                make_product(
                    "external-1",
                    name="External Python Book",
                    price="99.00",
                    tags=["python"],
                )
            ],
            num_items=1,
        )
    )

    assert [product.product_id for product in output.products] == ["external-1"]
    assert output.products[0].price == Decimal("99.00")
