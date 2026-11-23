"""Rule-based user profile agent with an optional Mock LLM explanation."""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.domain.agent_models import (
    PriceRange,
    UserBehaviorRecord,
    UserProfileInput,
    UserProfileOutput,
)
from agentic_commerce_platform.domain.enums import ProfileSource, UserSegment
from agentic_commerce_platform.domain.errors import ExternalServiceError
from agentic_commerce_platform.domain.models import AgentResult
from agentic_commerce_platform.domain.ports import UserBehaviorRepository
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider

__all__ = ["UserProfileAgent"]

logger = logging.getLogger(__name__)


class UserProfileAgent(BaseAgent):
    """Infer a deterministic user profile from in-memory behavior data.

    Structured facts are always derived by explicit rules. The injected LLM is
    only allowed to produce an explanation; its text never becomes a segment,
    preferred category, price range, or interest. A provider failure degrades to
    a rule-only profile with a structured warning.
    """

    def __init__(
        self,
        behavior_repository: UserBehaviorRepository,
        llm_provider: LLMProvider,
        *,
        name: str = "user_profile_agent",
        timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize the agent with injected dependencies.

        Args:
            behavior_repository: Read-only behavior data source.
            llm_provider: Explanation provider; never a source of profile facts.
            name: Stable agent name used in logs and results.
            timeout_seconds: Per-attempt timeout.
        """
        self._behavior_repository = behavior_repository
        self._llm_provider = llm_provider
        super().__init__(name=name, timeout_seconds=timeout_seconds)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Build a profile from a :class:`UserProfileInput` request."""
        request = kwargs.get("request")
        if not isinstance(request, UserProfileInput):
            raise ValueError("UserProfileAgent requires a UserProfileInput via 'request'")

        stored = self._behavior_repository.get_behavior(request.user_id)
        if stored is not None and stored.user_id != request.user_id:
            raise ValueError("behavior repository returned a record for a different user")

        behavior = self._merge_behavior(stored, request)
        segments = self._infer_segments(behavior)
        preferred_categories = self._preferred_categories(behavior)
        price_range = self._infer_price_range(behavior)
        recent_interests = self._recent_interests(behavior)
        confidence = self._confidence(behavior)

        source = ProfileSource.RULE_BASED
        explanation: str | None = None
        warnings: list[str] = []
        prompt = (
            "请解释以下规则画像，不得新增用户事实。"
            f"分群={','.join(segment.value for segment in segments)}；"
            f"偏好类目={','.join(preferred_categories) or 'unknown'}；"
            f"价格区间={price_range.min_price}-{price_range.max_price}。"
        )
        try:
            explanation = await self._llm_provider.generate(
                prompt,
                system_prompt=(
                    "你是阶段二画像解释助手。结构化画像由规则生成，"
                    "你只能解释，不得补充未提供的用户事实。"
                ),
                metadata={"phase": "phase-2", "agent": self.name, "mock": True},
            )
            source = ProfileSource.RULE_BASED_AND_MOCK_LLM
        except ExternalServiceError as exc:
            logger.warning(
                "profile_explanation_unavailable: %s",
                exc,
                extra={"agent_name": self.name},
            )
            warnings.append("mock_llm_unavailable")

        output = UserProfileOutput(
            user_id=request.user_id,
            segments=segments,
            preferred_categories=preferred_categories,
            price_range=price_range,
            recent_interests=recent_interests,
            confidence=confidence,
            profile_source=source,
            data_source=self._behavior_repository.source,
            explanation=explanation,
            warnings=warnings,
        )
        return AgentResult(
            agent_name=self.name,
            success=True,
            confidence=output.confidence,
            data=output.model_dump(mode="json"),
        )

    @staticmethod
    def _merge_behavior(
        stored: UserBehaviorRecord | None,
        request: UserProfileInput,
    ) -> UserBehaviorRecord:
        """Overlay explicitly supplied input values on the repository record."""
        base = stored or UserBehaviorRecord(user_id=request.user_id)
        return UserBehaviorRecord(
            user_id=request.user_id,
            recent_views=request.recent_views or base.recent_views,
            recent_clicks=request.recent_clicks or base.recent_clicks,
            recent_purchases=request.recent_purchases or base.recent_purchases,
            category_counts=request.category_counts or base.category_counts,
            average_order_value=(
                request.average_order_value
                if request.average_order_value is not None
                else base.average_order_value
            ),
            days_since_last_active=(
                request.days_since_last_active
                if request.days_since_last_active is not None
                else base.days_since_last_active
            ),
            account_age_days=(
                request.account_age_days
                if request.account_age_days is not None
                else base.account_age_days
            ),
        )

    @staticmethod
    def _infer_segments(behavior: UserBehaviorRecord) -> list[UserSegment]:
        """Apply deterministic segmentation rules."""
        interactions = (
            len(behavior.recent_views)
            + len(behavior.recent_clicks)
            + len(behavior.recent_purchases)
        )
        average_order_value = behavior.average_order_value
        is_new = (
            behavior.account_age_days is not None and behavior.account_age_days < 7
        ) or (
            behavior.account_age_days is None
            and interactions < 3
            and not behavior.recent_purchases
        )

        segments: list[UserSegment] = []
        if is_new:
            segments.append(UserSegment.NEW_USER)
        if (
            behavior.days_since_last_active is not None
            and behavior.days_since_last_active <= 7
            and interactions >= 3
        ):
            segments.append(UserSegment.ACTIVE)
        if average_order_value is not None and average_order_value <= Decimal("100"):
            segments.append(UserSegment.PRICE_SENSITIVE)
        if average_order_value is not None and average_order_value >= Decimal("500"):
            segments.append(UserSegment.HIGH_VALUE)
        if (
            behavior.days_since_last_active is not None
            and behavior.days_since_last_active >= 30
            and interactions > 0
            and not is_new
        ):
            segments.append(UserSegment.CHURN_RISK)

        if not segments:
            segments.append(
                UserSegment.CHURN_RISK
                if behavior.days_since_last_active is not None
                and behavior.days_since_last_active > 30
                else UserSegment.ACTIVE
            )
        return segments

    @staticmethod
    def _preferred_categories(behavior: UserBehaviorRecord) -> list[str]:
        """Return top categories by interaction count with stable tie-breaking."""
        ordered = sorted(
            (
                (category, count)
                for category, count in behavior.category_counts.items()
                if count > 0
            ),
            key=lambda item: (-item[1], item[0]),
        )
        return [category for category, _ in ordered[:3]]

    @staticmethod
    def _infer_price_range(behavior: UserBehaviorRecord) -> PriceRange:
        """Infer a conservative price interval from average order value."""
        average = behavior.average_order_value
        if average is None:
            return PriceRange(min_price=Decimal("0"), max_price=None)
        minimum = (average * Decimal("0.7")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        maximum = (average * Decimal("1.3")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return PriceRange(min_price=minimum, max_price=maximum)

    @staticmethod
    def _recent_interests(behavior: UserBehaviorRecord) -> list[str]:
        """Combine recent behavior identifiers in stable, deduplicated order."""
        interests: list[str] = []
        for item in [
            *behavior.recent_views,
            *behavior.recent_clicks,
            *behavior.recent_purchases,
        ]:
            if item not in interests:
                interests.append(item)
        return interests[:10]

    @staticmethod
    def _confidence(behavior: UserBehaviorRecord) -> float:
        """Return a bounded heuristic confidence based on available signals."""
        interactions = (
            len(behavior.recent_views)
            + len(behavior.recent_clicks)
            + len(behavior.recent_purchases)
        )
        confidence = 0.2 + min(0.45, interactions * 0.03)
        if behavior.category_counts:
            confidence += 0.1
        if behavior.average_order_value is not None:
            confidence += 0.1
        return round(min(0.9, confidence), 2)
