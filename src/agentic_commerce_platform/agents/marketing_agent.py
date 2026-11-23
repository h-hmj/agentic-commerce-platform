"""Marketing copy agent with rules-first generation and Mock LLM fallback."""

from __future__ import annotations

import logging
from typing import Any

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.domain.agent_models import (
    MarketingCopy,
    MarketingInput,
    MarketingOutput,
)
from agentic_commerce_platform.domain.enums import (
    MarketingProvider,
    MarketingStyle,
    UserSegment,
)
from agentic_commerce_platform.domain.errors import ExternalServiceError
from agentic_commerce_platform.domain.models import AgentResult, Product
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider

__all__ = ["MarketingAgent"]

logger = logging.getLogger(__name__)

_PROHIBITED_TERMS = ("国家级", "第一", "最好", "绝对", "100%")
_SAFE_LLM_LEADS = ("为你精选", "值得关注", "今日推荐", "不妨看看")


class MarketingAgent(BaseAgent):
    """Generate safe, product-specific copy using templates and optional Mock LLM.

    Product facts always come from deterministic templates. The LLM may only
    prepend one of a small whitelist of generic leads; any other text is ignored.
    This keeps the phase-two Mock from inventing product features. If the provider
    fails, the template copy is returned with ``provider=rule_based``.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        name: str = "marketing_agent",
        timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize the agent with its injected LLM provider."""
        self._llm_provider = llm_provider
        super().__init__(name=name, timeout_seconds=timeout_seconds)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Generate copy from a :class:`MarketingInput` request."""
        request = kwargs.get("request")
        if not isinstance(request, MarketingInput):
            raise ValueError("MarketingAgent requires a MarketingInput via 'request'")

        style = request.style or self._select_style(request)
        copies: list[MarketingCopy] = []
        for product in request.products:
            copies.append(await self._build_copy(product, style))
        output = MarketingOutput(copies=copies, style=style)
        return AgentResult(
            agent_name=self.name,
            success=True,
            data=output.model_dump(mode="json", by_alias=True),
        )

    async def _build_copy(
        self,
        product: Product,
        style: MarketingStyle,
    ) -> MarketingCopy:
        """Generate one copy item, falling back safely when the LLM fails."""
        fallback_copy = self._template_copy(product, style)
        copy_text = fallback_copy
        provider = MarketingProvider.RULE_BASED

        prompt = (
            f"为{style.value}风格选择一句简短开场语。"
            f"只能从以下短语中选择一个：{'、'.join(_SAFE_LLM_LEADS)}。"
            "不要添加商品事实或功效描述。"
        )
        try:
            candidate = await self._llm_provider.generate(
                prompt,
                system_prompt=(
                    "你是阶段二营销文案助手。当前为 Mock LLM 演示，"
                    "仅允许返回安全开场语，不得声称提供真实广告法审查。"
                ),
                metadata={
                    "phase": "phase-2",
                    "agent": self.name,
                    "style": style.value,
                    "product_id": product.product_id,
                },
            )
        except ExternalServiceError as exc:
            logger.warning(
                "marketing_llm_fallback: %s",
                exc,
                extra={"agent_name": self.name},
            )
        else:
            normalized_candidate = candidate.strip().strip("。.!！")
            if normalized_candidate in _SAFE_LLM_LEADS:
                copy_text = f"{normalized_candidate}。{fallback_copy}"
                provider = MarketingProvider.MOCK

        warnings = [
            f"risk_term:{term}" for term in _PROHIBITED_TERMS if term in copy_text
        ]
        return MarketingCopy(
            product_id=product.product_id,
            copy_text=copy_text,
            style=style,
            compliance_passed=not warnings,
            warnings=warnings,
            provider=provider,
        )

    @staticmethod
    def _select_style(request: MarketingInput) -> MarketingStyle:
        """Choose a marketing style from the profile's rule-derived segments."""
        segments = set(request.user_profile.segments)
        if UserSegment.CHURN_RISK in segments:
            return MarketingStyle.RECALL
        if UserSegment.NEW_USER in segments:
            return MarketingStyle.WELCOME
        if UserSegment.HIGH_VALUE in segments:
            return MarketingStyle.PREMIUM
        if UserSegment.PRICE_SENSITIVE in segments:
            return MarketingStyle.VALUE
        if UserSegment.ACTIVE in segments:
            return MarketingStyle.ACTIVE
        return MarketingStyle.VALUE

    @staticmethod
    def _template_copy(product: Product, style: MarketingStyle) -> str:
        """Build a deterministic copy using only real product fields."""
        price = f"{product.price:.2f}"
        if style is MarketingStyle.WELCOME:
            return (
                f"{product.name} 已加入你的探索清单，"
                f"来自{product.category}类目，售价 ¥{price}。"
            )
        if style is MarketingStyle.VALUE:
            return (
                f"{product.name} 来自{product.category}类目，"
                f"售价 ¥{price}，适合关注实用价值的你。"
            )
        if style is MarketingStyle.PREMIUM:
            return (
                f"精选{product.category}类目商品 {product.name}，"
                f"售价 ¥{price}，适合注重品质体验的你。"
            )
        if style is MarketingStyle.ACTIVE:
            return (
                f"根据你近期的兴趣，推荐看看{product.category}类目中的 "
                f"{product.name}，售价 ¥{price}。"
            )
        return (
            f"久未相见，{product.name} 仍在{product.category}类目等你，"
            f"售价 ¥{price}。"
        )
