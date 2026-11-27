"""Rule-based user profile agent with an optional Mock LLM explanation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.domain.agent_models import (
    PriceRange,
    UserBehaviorRecord,
    UserProfileInput,
    UserProfileOutput,
)
from agentic_commerce_platform.domain.data_models import BehaviorEvent, PersistedUserProfile
from agentic_commerce_platform.domain.enums import BehaviorType, ProfileSource, UserSegment
from agentic_commerce_platform.domain.errors import ExternalServiceError
from agentic_commerce_platform.domain.models import AgentResult
from agentic_commerce_platform.domain.ports import (
    MemoryStore,
    UserBehaviorRepository,
    UserProfileRepository,
)
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
        profile_repository: UserProfileRepository | None = None,
        memory_store: MemoryStore | None = None,
        cache_ttl_seconds: int = 300,
        name: str = "user_profile_agent",
        timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize the agent with injected dependencies.

        Args:
            behavior_repository: Read-only historical behavior data source.
            llm_provider: Explanation provider; never a source of profile facts.
            profile_repository: Optional long-term profile persistence.
            memory_store: Optional Redis/in-memory short-term behavior and cache.
            cache_ttl_seconds: TTL for profile caching.
            name: Stable agent name used in logs and results.
            timeout_seconds: Per-attempt timeout.
        """
        self._behavior_repository = behavior_repository
        self._llm_provider = llm_provider
        self._profile_repository = profile_repository
        self._memory_store = memory_store
        self._cache_ttl_seconds = cache_ttl_seconds
        super().__init__(name=name, timeout_seconds=timeout_seconds)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Build a profile from a :class:`UserProfileInput` request."""
        request = kwargs.get("request")
        if not isinstance(request, UserProfileInput):
            raise ValueError("UserProfileAgent requires a UserProfileInput via 'request'")

        warnings: list[str] = []
        memory_source: str | None = None
        data_source = self._behavior_repository.source
        behavior: UserBehaviorRecord | None = None

        if self._has_explicit_behavior(request):
            behavior = self._behavior_from_request(request)
        else:
            if self._memory_store is not None:
                try:
                    events = await self._memory_store.get_recent_behaviors(
                        request.user_id,
                        limit=100,
                    )
                except Exception as exc:
                    logger.warning(
                        "profile_memory_read_failed: %s",
                        exc,
                        extra={"agent_name": self.name},
                        exc_info=True,
                    )
                    warnings.append("memory_read_failed")
                else:
                    if events:
                        behavior = self._events_to_behavior(request.user_id, events)
                        data_source = self._memory_store.source
                        memory_source = self._memory_store.source.value

            if behavior is None and self._memory_store is not None:
                try:
                    cached = await self._memory_store.get_cached_profile(request.user_id)
                except Exception as exc:
                    logger.warning(
                        "profile_cache_read_failed: %s",
                        exc,
                        extra={"agent_name": self.name},
                        exc_info=True,
                    )
                    warnings.append("profile_cache_read_failed")
                else:
                    if cached is not None:
                        return AgentResult(
                            agent_name=self.name,
                            success=True,
                            confidence=cached.confidence,
                            data=cached.model_copy(
                                update={
                                    "memory_source": self._memory_store.source.value
                                }
                            ).model_dump(mode="json"),
                        )

            if behavior is None:
                stored = self._behavior_repository.get_behavior(request.user_id)
                if stored is not None and stored.user_id != request.user_id:
                    raise ValueError(
                        "behavior repository returned a record for a different user"
                    )
                if stored is not None:
                    behavior = self._merge_behavior(stored, request)
                    data_source = self._behavior_repository.source

            if behavior is None and self._profile_repository is not None:
                try:
                    persisted = self._profile_repository.get_profile(request.user_id)
                except Exception as exc:
                    logger.warning(
                        "profile_persistence_read_failed: %s",
                        exc,
                        extra={"agent_name": self.name},
                        exc_info=True,
                    )
                    warnings.append("profile_persistence_read_failed")
                else:
                    if persisted is not None:
                        return self._persisted_result(persisted)

            if behavior is None:
                behavior = UserBehaviorRecord(user_id=request.user_id)

        segments = self._infer_segments(behavior)
        preferred_categories = self._preferred_categories(behavior)
        price_range = self._infer_price_range(behavior)
        recent_interests = self._recent_interests(behavior)
        confidence = self._confidence(behavior)

        source = ProfileSource.RULE_BASED
        explanation: str | None = None
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
                    "你是阶段四画像解释助手。结构化画像由规则生成，"
                    "你只能解释，不得补充未提供的用户事实。"
                ),
                metadata={"phase": "phase-4", "agent": self.name, "mock": True},
            )
            source = ProfileSource.RULE_BASED_AND_MOCK_LLM
        except ExternalServiceError as exc:
            logger.warning(
                "profile_explanation_unavailable: %s",
                exc,
                extra={"agent_name": self.name},
            )
            warnings.append("mock_llm_unavailable")

        profile_persisted = False
        output = UserProfileOutput(
            user_id=request.user_id,
            segments=segments,
            preferred_categories=preferred_categories,
            price_range=price_range,
            recent_interests=recent_interests,
            confidence=confidence,
            profile_source=source,
            data_source=data_source,
            memory_source=memory_source,
            profile_persisted=False,
            explanation=explanation,
            warnings=warnings,
        )

        if self._profile_repository is not None:
            try:
                self._profile_repository.save_profile(output)
            except Exception as exc:
                logger.warning(
                    "profile_persistence_failed: %s",
                    exc,
                    extra={"agent_name": self.name},
                    exc_info=True,
                )
                warnings.append("profile_persistence_failed")
            else:
                profile_persisted = True

        final_output = output.model_copy(
            update={
                "profile_persisted": profile_persisted,
                "warnings": list(dict.fromkeys(warnings)),
            }
        )
        if self._memory_store is not None:
            try:
                await self._memory_store.cache_profile(
                    final_output,
                    ttl_seconds=self._cache_ttl_seconds,
                )
            except Exception as exc:
                logger.warning(
                    "profile_cache_write_failed: %s",
                    exc,
                    extra={"agent_name": self.name},
                    exc_info=True,
                )
                final_output = final_output.model_copy(
                    update={
                        "warnings": [
                            *final_output.warnings,
                            "profile_cache_write_failed",
                        ]
                    }
                )

        return AgentResult(
            agent_name=self.name,
            success=True,
            confidence=final_output.confidence,
            data=final_output.model_dump(mode="json"),
        )

    def _persisted_result(self, persisted: PersistedUserProfile) -> AgentResult:
        """Return a stored profile without inventing new facts or re-explaining it."""
        return AgentResult(
            agent_name=self.name,
            success=True,
            confidence=persisted.profile.confidence,
            data=persisted.profile.model_copy(
                update={"profile_persisted": True}
            ).model_dump(mode="json"),
        )

    @staticmethod
    def _has_explicit_behavior(request: UserProfileInput) -> bool:
        """Return whether the caller supplied behavior beyond the user ID."""
        return bool(
            request.recent_views
            or request.recent_clicks
            or request.recent_purchases
            or request.category_counts
            or request.average_order_value is not None
            or request.days_since_last_active is not None
            or request.account_age_days is not None
        )

    @staticmethod
    def _behavior_from_request(request: UserProfileInput) -> UserBehaviorRecord:
        """Convert explicit input fields into a behavior value object."""
        return UserBehaviorRecord(
            user_id=request.user_id,
            recent_views=request.recent_views,
            recent_clicks=request.recent_clicks,
            recent_purchases=request.recent_purchases,
            category_counts=request.category_counts,
            average_order_value=request.average_order_value,
            days_since_last_active=request.days_since_last_active,
            account_age_days=request.account_age_days,
        )

    @staticmethod
    def _events_to_behavior(
        user_id: str,
        events: list[BehaviorEvent],
    ) -> UserBehaviorRecord:
        """Summarize bounded real-time events into rule inputs."""
        views: list[str] = []
        clicks: list[str] = []
        purchases: list[str] = []
        amounts: list[Decimal] = []
        categories: dict[str, int] = {}
        for event in events:
            if event.item_id:
                if event.behavior_type is BehaviorType.VIEW:
                    views.append(event.item_id)
                elif event.behavior_type is BehaviorType.CLICK:
                    clicks.append(event.item_id)
                else:
                    purchases.append(event.item_id)
                    if event.amount is not None:
                        amounts.append(event.amount)
            if event.category:
                categories[event.category] = categories.get(event.category, 0) + 1
        latest = max((event.occurred_at for event in events), default=None)
        days_since_active = (
            max(0, (datetime.now(UTC) - latest).days) if latest is not None else None
        )
        return UserBehaviorRecord(
            user_id=user_id,
            recent_views=list(dict.fromkeys(views))[:100],
            recent_clicks=list(dict.fromkeys(clicks))[:100],
            recent_purchases=list(dict.fromkeys(purchases))[:100],
            category_counts=categories,
            average_order_value=(
                sum(amounts, Decimal("0")) / len(amounts) if amounts else None
            ),
            days_since_last_active=days_since_active,
            account_age_days=None,
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
