"""Regression tests for phase-one and phase-two behavior after phase three."""

from __future__ import annotations

from agentic_commerce_platform.domain.enums import RecommendationStatus
from agentic_commerce_platform.domain.models import RecommendationRequest
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
from agentic_commerce_platform.services.recommendation_service import RecommendationService
from agentic_commerce_platform.domain.agent_models import (
    CatalogInput,
    InventoryInput,
    MarketingInput,
    RecommendationInput,
    UserProfileInput,
)


async def test_phase_two_services_are_still_independently_callable() -> None:
    """Phase-three orchestration does not couple the phase-two single-agent services."""
    provider = MockLLMProvider()
    profile_service = ProfileService(InMemoryUserBehaviorRepository(), provider)
    catalog_service = CatalogService(InMemoryCatalogRepository(), provider)
    recommendation_service = ProductRecommendationService(provider)
    inventory_service = InventoryService(InMemoryInventoryRepository(), provider)
    marketing_service = MarketingService(provider)

    profile = await profile_service.build_profile(
        UserProfileInput(user_id="u-demo-001")
    )
    catalog = await catalog_service.search_products(
        CatalogInput(query="python", limit=3)
    )
    recommendation = await recommendation_service.recommend_products(
        RecommendationInput(
            user_profile=profile,
            candidate_products=catalog.products,
            num_items=2,
        )
    )
    inventory = await inventory_service.evaluate_inventory(
        InventoryInput(products=catalog.products, low_stock_threshold=3)
    )
    marketing = await marketing_service.generate_copies(
        MarketingInput(user_profile=profile, products=catalog.products[:2])
    )

    assert profile.user_id == "u-demo-001"
    assert catalog.products
    assert recommendation.strategy.value == "rule_based_demo"
    assert inventory.source.value == "in_memory_demo"
    assert marketing.copies


async def test_phase_one_skeleton_service_is_unchanged() -> None:
    """The phase-one skeleton service still returns status=skeleton."""
    service = RecommendationService(MockLLMProvider())

    response = await service.recommend(
        RecommendationRequest(user_id="regression-user"),
        request_id="regression-skeleton",
    )

    assert response.status is RecommendationStatus.SKELETON
    assert response.products == []
    assert "demo_agent" in response.agent_results
