"""Tests for MarketingAgent styles, compliance, and safe LLM fallback."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from agentic_commerce_platform.agents.marketing_agent import MarketingAgent
from agentic_commerce_platform.domain.agent_models import MarketingInput, MarketingOutput
from agentic_commerce_platform.domain.enums import (
    MarketingProvider,
    MarketingStyle,
    UserSegment,
)
from agentic_commerce_platform.infrastructure.llm import MockLLMProvider
from tests.helpers import make_product, make_profile, parse_output

_PRODUCT = make_product(
    "p-1",
    name="Python 编程实战",
    category="books",
    price="89.00",
    tags=["python", "backend"],
)


@pytest.mark.parametrize(
    ("segment", "expected_style"),
    [
        (UserSegment.NEW_USER, MarketingStyle.WELCOME),
        (UserSegment.ACTIVE, MarketingStyle.ACTIVE),
        (UserSegment.PRICE_SENSITIVE, MarketingStyle.VALUE),
        (UserSegment.HIGH_VALUE, MarketingStyle.PREMIUM),
        (UserSegment.CHURN_RISK, MarketingStyle.RECALL),
    ],
)
async def test_style_is_selected_from_user_segment(
    segment: UserSegment,
    expected_style: MarketingStyle,
) -> None:
    """Each supported user segment maps to a deterministic copy style."""
    profile = make_profile(segments=[segment])
    provider = MockLLMProvider(response="为你精选")
    agent = MarketingAgent(provider)

    output = parse_output(
        await agent.run(
            request=MarketingInput(user_profile=profile, products=[_PRODUCT])
        ),
        MarketingOutput,
    )

    assert output.style is expected_style
    assert output.copies[0].style is expected_style


async def test_explicit_style_override() -> None:
    """An explicit request style takes precedence over profile inference."""
    profile = make_profile(segments=[UserSegment.NEW_USER])
    agent = MarketingAgent(MockLLMProvider(response="值得关注"))

    output = parse_output(
        await agent.run(
            request=MarketingInput(
                user_profile=profile,
                products=[_PRODUCT],
                style=MarketingStyle.PREMIUM,
            )
        ),
        MarketingOutput,
    )

    assert output.style is MarketingStyle.PREMIUM


async def test_copy_uses_real_product_fields() -> None:
    """Fallback copy contains only facts supplied by the product model."""
    profile = make_profile()
    agent = MarketingAgent(MockLLMProvider())

    output = parse_output(
        await agent.run(
            request=MarketingInput(user_profile=profile, products=[_PRODUCT])
        ),
        MarketingOutput,
    )
    item = output.copies[0]

    assert item.product_id == _PRODUCT.product_id
    assert _PRODUCT.name in item.copy_text
    assert _PRODUCT.category in item.copy_text
    assert "89.00" in item.copy_text
    assert item.provider is MarketingProvider.RULE_BASED
    assert item.compliance_passed is True


async def test_mock_llm_success_provider_marker() -> None:
    """A product-specific Mock response is accepted and marked as mock."""
    profile = make_profile()
    provider = MockLLMProvider(response="为你精选")
    agent = MarketingAgent(provider)

    output = parse_output(
        await agent.run(
            request=MarketingInput(user_profile=profile, products=[_PRODUCT])
        ),
        MarketingOutput,
    )
    item = output.copies[0]

    assert item.provider is MarketingProvider.MOCK
    assert item.copy_text.startswith("为你精选。")
    assert _PRODUCT.name in item.copy_text
    assert item.compliance_passed is True


async def test_unapproved_llm_text_is_not_used() -> None:
    """The LLM cannot inject unverified product claims into final copy."""
    profile = make_profile()
    provider = MockLLMProvider(response="绝对防水，续航100天，国家级认证。")
    agent = MarketingAgent(provider)

    output = parse_output(
        await agent.run(
            request=MarketingInput(user_profile=profile, products=[_PRODUCT])
        ),
        MarketingOutput,
    )
    item = output.copies[0]

    assert item.provider is MarketingProvider.RULE_BASED
    assert "防水" not in item.copy_text
    assert "续航100天" not in item.copy_text


async def test_prohibited_terms_fail_compliance() -> None:
    """Risk terms in real product fields are flagged for review."""
    risky_product = make_product(
        "p-risky",
        name="国家级第一最好绝对100%好物",
        category="books",
        price="99.00",
    )
    profile = make_profile()
    agent = MarketingAgent(MockLLMProvider())

    output = parse_output(
        await agent.run(
            request=MarketingInput(user_profile=profile, products=[risky_product])
        ),
        MarketingOutput,
    )
    item = output.copies[0]

    assert item.compliance_passed is False
    assert set(item.warnings) == {
        "risk_term:国家级",
        "risk_term:第一",
        "risk_term:最好",
        "risk_term:绝对",
        "risk_term:100%",
    }


async def test_mock_llm_failure_uses_safe_rule_based_copy() -> None:
    """Provider failure degrades to the deterministic template."""
    profile = make_profile()
    agent = MarketingAgent(
        MockLLMProvider(fail=True, failure_message="marketing mock unavailable")
    )

    result = await agent.run(
        request=MarketingInput(user_profile=profile, products=[_PRODUCT])
    )
    output = parse_output(result, MarketingOutput)
    item = output.copies[0]

    assert result.success is True
    assert item.provider is MarketingProvider.RULE_BASED
    assert _PRODUCT.name in item.copy_text
    assert "89.00" in item.copy_text


async def test_each_copy_uses_its_own_product_id() -> None:
    """Multiple products receive separate, correctly associated copies."""
    second_product = make_product(
        "p-2",
        name="数据科学入门",
        category="books",
        price="129.00",
    )

    class PerProductProvider:
        async def generate(
            self,
            prompt: str,
            *,
            system_prompt: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> str:
            return "为你精选"

    agent = MarketingAgent(PerProductProvider())
    output = parse_output(
        await agent.run(
            request=MarketingInput(
                user_profile=make_profile(),
                products=[_PRODUCT, second_product],
            )
        ),
        MarketingOutput,
    )

    assert [copy.product_id for copy in output.copies] == ["p-1", "p-2"]
    assert "Python 编程实战" in output.copies[0].copy_text
    assert "数据科学入门" in output.copies[1].copy_text


async def test_empty_products_return_empty_copies() -> None:
    """No products means no LLM call is required and no copies are returned."""
    agent = MarketingAgent(MockLLMProvider(fail=True))

    result = await agent.run(
        request=MarketingInput(user_profile=make_profile(), products=[])
    )
    output = parse_output(result, MarketingOutput)

    assert result.success is True
    assert output.copies == []


def test_invalid_marketing_style_is_rejected() -> None:
    """Unknown style values fail Pydantic validation."""
    with pytest.raises(ValidationError):
        MarketingInput(
            user_profile=make_profile(),
            products=[],
            style="unsupported-style",
        )
