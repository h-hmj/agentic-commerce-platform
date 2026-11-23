"""Tests for deterministic RecommendationAgent ranking and diversity rules."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agentic_commerce_platform.agents.recommendation_agent import RecommendationAgent
from agentic_commerce_platform.domain.agent_models import (
    RecommendationInput,
    RecommendationOutput,
)
from agentic_commerce_platform.domain.enums import RecommendationReasonCode, UserSegment
from agentic_commerce_platform.infrastructure.llm import MockLLMProvider
from tests.helpers import make_product, make_profile, parse_output

_PROFILE = make_profile(
    segments=[UserSegment.ACTIVE, UserSegment.HIGH_VALUE],
    preferred_categories=["books"],
    min_price="50.00",
    max_price="200.00",
    recent_interests=["python"],
    confidence=0.9,
)

_PRODUCTS = [
    make_product("p-1", category="books", price="100.00", stock=5, tags=["python"]),
    make_product("p-2", category="books", price="180.00", stock=2, tags=["architecture"]),
    make_product("p-3", category="electronics", price="120.00", stock=3, tags=["python"]),
    make_product("p-4", category="books", price="300.00", stock=5, tags=["python"]),
    make_product("p-5", category="books", price="90.00", stock=0, tags=["python"]),
    make_product("p-7", category="home", price="80.00", stock=1, tags=["coffee"]),
    make_product("p-8", category="electronics", price="110.00", stock=1, tags=["python"]),
]


def _input(products=None, num_items: int = 5) -> RecommendationInput:
    return RecommendationInput(
        user_profile=_PROFILE,
        candidate_products=_PRODUCTS if products is None else products,
        num_items=num_items,
    )


async def test_category_and_price_match_reasons() -> None:
    """Matching category and price produce structured reason codes."""
    result = await RecommendationAgent(MockLLMProvider()).run(request=_input())
    output = parse_output(result, RecommendationOutput)

    p1_reasons = {reason.code for reason in output.ranking_reasons["p-1"]}
    p4_reasons = {reason.code for reason in output.ranking_reasons["p-4"]}

    assert RecommendationReasonCode.CATEGORY_MATCH in p1_reasons
    assert RecommendationReasonCode.WITHIN_PRICE_RANGE in p1_reasons
    assert RecommendationReasonCode.IN_STOCK in p1_reasons
    assert RecommendationReasonCode.TAG_MATCH in p1_reasons
    assert RecommendationReasonCode.WITHIN_PRICE_RANGE not in p4_reasons


async def test_out_of_stock_products_are_filtered() -> None:
    """Out-of-stock candidates are excluded and counted in filtered_count."""
    result = await RecommendationAgent(MockLLMProvider()).run(request=_input())
    output = parse_output(result, RecommendationOutput)

    assert "p-5" not in {product.product_id for product in output.products}
    assert output.filtered_count >= 1


async def test_duplicate_product_ids_are_deduplicated() -> None:
    """The same product ID is never returned twice."""
    duplicate_products = [_PRODUCTS[0], _PRODUCTS[0], _PRODUCTS[1]]
    result = await RecommendationAgent(MockLLMProvider()).run(
        request=_input(duplicate_products, num_items=5)
    )
    output = parse_output(result, RecommendationOutput)

    product_ids = [product.product_id for product in output.products]
    assert len(product_ids) == len(set(product_ids))
    assert output.filtered_count == 1


async def test_num_items_limit_is_enforced() -> None:
    """The agent does not return more than the requested number of items."""
    result = await RecommendationAgent(MockLLMProvider()).run(
        request=_input(num_items=2)
    )
    output = parse_output(result, RecommendationOutput)

    assert len(output.products) == 2


async def test_category_diversity_cap() -> None:
    """At most two products from the same category are selected."""
    result = await RecommendationAgent(MockLLMProvider()).run(
        request=_input(num_items=8)
    )
    output = parse_output(result, RecommendationOutput)
    category_counts: dict[str, int] = {}
    for product in output.products:
        category_counts[product.category] = category_counts.get(product.category, 0) + 1

    assert all(count <= 2 for count in category_counts.values())
    assert len(category_counts) >= 2
    all_reasons = [
        reason.code
        for reasons in output.ranking_reasons.values()
        for reason in reasons
    ]
    assert RecommendationReasonCode.DIVERSITY_BONUS in all_reasons


async def test_empty_candidate_set() -> None:
    """An empty candidate set returns a valid empty selection."""
    result = await RecommendationAgent(MockLLMProvider()).run(
        request=RecommendationInput(
            user_profile=_PROFILE,
            candidate_products=[],
            num_items=5,
        )
    )
    output = parse_output(result, RecommendationOutput)

    assert output.products == []
    assert output.ranking_reasons == {}
    assert output.filtered_count == 0
    assert output.confidence == 0.0


async def test_ranking_is_stable_across_candidate_input_order() -> None:
    """Tie-breaking is stable and independent of candidate input order."""
    agent = RecommendationAgent(MockLLMProvider())

    first = parse_output(await agent.run(request=_input()), RecommendationOutput)
    reversed_input = RecommendationInput(
        user_profile=_PROFILE,
        candidate_products=list(reversed(_PRODUCTS)),
        num_items=5,
    )
    second = parse_output(await agent.run(request=reversed_input), RecommendationOutput)

    first_ids = [product.product_id for product in first.products]
    second_ids = [product.product_id for product in second.products]
    assert first_ids == second_ids


async def test_ranking_does_not_call_llm() -> None:
    """Rule-based ranking succeeds even when the injected provider is failing."""
    agent = RecommendationAgent(MockLLMProvider(fail=True))

    result = await agent.run(request=_input())

    assert result.success is True
    assert result.error is None


async def test_output_has_reasons_for_every_product() -> None:
    """Each returned product has a complete structured reason list."""
    output = parse_output(
        await RecommendationAgent(MockLLMProvider()).run(request=_input()),
        RecommendationOutput,
    )

    assert set(output.ranking_reasons) == {
        product.product_id for product in output.products
    }
    assert all(reasons for reasons in output.ranking_reasons.values())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"num_items": 0},
        {"num_items": 51},
    ],
)
def test_invalid_recommendation_input(kwargs: dict[str, object]) -> None:
    """Invalid item counts are rejected by the input model."""
    with pytest.raises(ValidationError):
        RecommendationInput(
            user_profile=_PROFILE,
            candidate_products=[],
            **kwargs,
        )
