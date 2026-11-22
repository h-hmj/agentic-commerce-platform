"""Phase-one demonstration agent used only to exercise the platform wiring."""

from __future__ import annotations

from typing import Any

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.domain.models import AgentResult, RecommendationRequest
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider

__all__ = ["DemoAgent"]


class DemoAgent(BaseAgent):
    """Minimal agent that asks the configured LLM for a non-recommendation ack.

    This is not a business agent. It exists to prove that the API, service,
    agent lifecycle, logging, and provider abstraction are connected. It does
    not retrieve products, rank items, or produce real recommendations.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        name: str = "demo_agent",
        timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize the demo agent.

        Args:
            llm_provider: Provider used for the demonstration call.
            name: Logical agent name used in results and logs.
            timeout_seconds: Per-attempt execution timeout.
        """
        self._llm_provider = llm_provider
        super().__init__(name=name, timeout_seconds=timeout_seconds)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Call the provider with a clearly labeled phase-one prompt.

        Args:
            **kwargs: Must contain ``request`` as a
                :class:`RecommendationRequest`.

        Returns:
            Agent result containing the mock provider output and a disclaimer.

        Raises:
            ValueError: If the structured request keyword is missing or invalid.
        """
        request = kwargs.get("request")
        if not isinstance(request, RecommendationRequest):
            raise ValueError("DemoAgent requires a RecommendationRequest via 'request'")

        prompt = (
            f"阶段一链路检查。场景={request.scene.value}，"
            f"语言={request.context.locale}，期望数量={request.num_items}。"
            "请只返回一句工程链路确认，不要生成商品推荐。"
        )
        system_prompt = (
            "你是阶段一 DemoAgent。当前使用离线 Mock LLM。"
            "不得声称产生了真实推荐或真实大模型结果。"
        )
        llm_output = await self._llm_provider.generate(
            prompt,
            system_prompt=system_prompt,
            metadata={"phase": "phase-1", "agent": self.name, "mock": True},
        )

        return AgentResult(
            agent_name=self.name,
            success=True,
            latency_ms=0.0,
            error=None,
            confidence=None,
            data={
                "phase": "phase-1",
                "demo": True,
                "provider": "mock",
                "llm_output": llm_output,
                "disclaimer": (
                    "DemoAgent + MockLLMProvider output only; not a real "
                    "recommendation and not a real LLM result."
                ),
            },
        )
