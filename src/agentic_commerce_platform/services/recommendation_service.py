"""Phase-one recommendation service orchestration."""

from __future__ import annotations

import logging
import time
from uuid import uuid4

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.agents.demo import DemoAgent
from agentic_commerce_platform.domain.enums import RecommendationStatus
from agentic_commerce_platform.domain.errors import AgentExecutionError
from agentic_commerce_platform.domain.models import RecommendationRequest, RecommendationResponse
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider
from agentic_commerce_platform.infrastructure.observability.logging import request_log_context

__all__ = ["RecommendationService"]

logger = logging.getLogger(__name__)

_SKELETON_MESSAGES = (
    "阶段一工程骨架已运行，真实推荐流程将在后续阶段实现。",
    "当前使用 DemoAgent 与 MockLLMProvider，响应不是真实商品推荐。",
)


class RecommendationService:
    """Coordinate the phase-one recommendation request lifecycle.

    The service creates correlation IDs, invokes a demonstration agent, converts
    its structured output into an API response, measures latency, and translates
    agent failures into project-level exceptions. It deliberately returns no
    products: the real retrieval and ranking flows belong to later phases.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        agent: BaseAgent | None = None,
    ) -> None:
        """Initialize the service and its demonstration agent.

        Args:
            llm_provider: Provider used by the default demonstration agent.
            agent: Optional agent injection point for tests or future wiring.
        """
        self._llm_provider = llm_provider
        self._agent = agent if agent is not None else DemoAgent(llm_provider)

    @property
    def agent(self) -> BaseAgent:
        """Return the agent used by this service (read-only access)."""
        return self._agent

    async def recommend(
        self,
        request: RecommendationRequest,
        *,
        request_id: str | None = None,
    ) -> RecommendationResponse:
        """Produce a phase-one skeleton recommendation response.

        Args:
            request: Validated recommendation request.
            request_id: Optional correlation ID supplied by the API layer. A new
                UUID is generated when omitted.

        Returns:
            A response with ``status='skeleton'``, no products, and the demo
            agent's structured result.

        Raises:
            AgentExecutionError: If the demo agent fails or the service cannot
                produce a response. The original exception is retained as the
                cause when available.
        """
        effective_request_id = (
            request_id.strip() if request_id and request_id.strip() else uuid4().hex
        )
        started_at = time.perf_counter()

        with request_log_context(effective_request_id):
            logger.info(
                "recommendation_started",
                extra={
                    "agent_name": self._agent.name,
                    "scene": request.scene.value,
                    "num_items": request.num_items,
                },
            )

            try:
                result = await self._agent.run(request=request)
            except AgentExecutionError:
                logger.error(
                    "recommendation_failed",
                    extra={"agent_name": self._agent.name},
                    exc_info=True,
                )
                raise
            except Exception as exc:
                logger.exception(
                    "recommendation_failed",
                    extra={"agent_name": self._agent.name},
                )
                raise AgentExecutionError(
                    "Recommendation service failed while executing the demo agent.",
                    agent_name=self._agent.name,
                ) from exc

            if not result.success:
                logger.error(
                    "recommendation_agent_failed",
                    extra={"agent_name": result.agent_name},
                )
                raise AgentExecutionError(
                    f"Agent '{result.agent_name}' returned a failed result.",
                    agent_name=result.agent_name,
                    details={"agent_error": result.error},
                )

            total_latency_ms = (time.perf_counter() - started_at) * 1000.0
            response = RecommendationResponse(
                request_id=effective_request_id,
                user_id=request.user_id,
                status=RecommendationStatus.SKELETON,
                products=[],
                messages=list(_SKELETON_MESSAGES),
                agent_results={result.agent_name: result},
                total_latency_ms=total_latency_ms,
            )

            logger.info(
                "recommendation_completed",
                extra={
                    "agent_name": self._agent.name,
                    "duration_ms": round(total_latency_ms, 2),
                },
            )
            return response
