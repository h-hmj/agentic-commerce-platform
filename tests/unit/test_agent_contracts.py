"""Cross-agent contracts that keep the phase-two design consistent."""

from __future__ import annotations

from pydantic import BaseModel

from agentic_commerce_platform.agents import (
    BaseAgent,
    CatalogAgent,
    InventoryAgent,
    MarketingAgent,
    RecommendationAgent,
    UserProfileAgent,
)
from agentic_commerce_platform.domain.agent_models import (
    CatalogInput,
    CatalogOutput,
    InventoryInput,
    InventoryOutput,
    MarketingCopy,
    MarketingInput,
    MarketingOutput,
    RecommendationInput,
    RecommendationOutput,
    UserProfileInput,
    UserProfileOutput,
)
from agentic_commerce_platform.infrastructure.data import (
    DEMO_DATA_DISCLAIMER,
    InMemoryCatalogRepository,
    InMemoryInventoryRepository,
    InMemoryUserBehaviorRepository,
)
from agentic_commerce_platform.infrastructure.llm import MockLLMProvider


def test_all_professional_agents_follow_base_contract() -> None:
    """All five agents are BaseAgent subclasses with stable unique names."""
    llm = MockLLMProvider()
    agents = [
        UserProfileAgent(InMemoryUserBehaviorRepository(), llm),
        CatalogAgent(InMemoryCatalogRepository(), llm),
        RecommendationAgent(llm),
        InventoryAgent(InMemoryInventoryRepository(), llm),
        MarketingAgent(llm),
    ]

    assert all(isinstance(agent, BaseAgent) for agent in agents)
    assert [agent.name for agent in agents] == [
        "user_profile_agent",
        "catalog_agent",
        "recommendation_agent",
        "inventory_agent",
        "marketing_agent",
    ]
    assert len({agent.name for agent in agents}) == 5


def test_agent_inputs_and_outputs_are_pydantic_models() -> None:
    """Every professional agent has a structured Pydantic input and output."""
    contract_types = [
        CatalogInput,
        CatalogOutput,
        InventoryInput,
        InventoryOutput,
        MarketingInput,
        MarketingOutput,
        RecommendationInput,
        RecommendationOutput,
        UserProfileInput,
        UserProfileOutput,
    ]

    assert all(issubclass(model, BaseModel) for model in contract_types)


def test_marketing_copy_serializes_required_copy_alias() -> None:
    """The marketing output keeps the required ``copy`` JSON field name."""
    copy = MarketingCopy(
        product_id="p-1",
        copy_text="safe product copy",
        style="value",
        compliance_passed=True,
        warnings=[],
        provider="rule_based",
    )

    payload = copy.model_dump(mode="json", by_alias=True)

    assert payload["copy"] == "safe product copy"
    assert "copy_text" not in payload


def test_demo_data_is_explicitly_marked() -> None:
    """Demo data carries explicit phase-two in-memory provenance."""
    assert "Phase-2 in-memory demo data" in DEMO_DATA_DISCLAIMER
    assert "Not real catalog" in DEMO_DATA_DISCLAIMER
