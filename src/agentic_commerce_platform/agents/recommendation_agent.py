"""Deterministic rule-based product recommendation agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.domain.agent_models import (
    RankingReason,
    RecommendationInput,
    RecommendationOutput,
)
from agentic_commerce_platform.domain.enums import (
    RecommendationReasonCode,
    RecommendationStrategy,
)
from agentic_commerce_platform.domain.models import AgentResult, Product
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider

__all__ = ["RecommendationAgent"]

_MAX_SCORE = 80
_MAX_PER_CATEGORY = 2
_DIVERSITY_BONUS = 5


@dataclass
class _Candidate:
    """Internal ranked candidate with its pre-diversity rule score."""

    product: Product
    base_score: int
    reasons: list[RankingReason] = field(default_factory=list)


class RecommendationAgent(BaseAgent):
    """Rank externally supplied candidates using deterministic business rules.

    Ranking uses category, price range, stock, tags, and a category cap for
    diversity. The injected LLM is never consulted for ranking; structured
    reasons and order remain deterministic for a given input.
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        *,
        name: str = "recommendation_agent",
        timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize the agent with the uniform LLM dependency."""
        self._llm_provider = llm_provider
        super().__init__(name=name, timeout_seconds=timeout_seconds)

    async def execute(self, **kwargs: Any) -> AgentResult:
        """Rank candidates from a :class:`RecommendationInput` request."""
        request = kwargs.get("request")
        if not isinstance(request, RecommendationInput):
            raise ValueError(
                "RecommendationAgent requires a RecommendationInput via 'request'"
            )

        candidates, filtered_count = self._prepare_candidates(request)
        selected = self._select_with_diversity(candidates, request.num_items)
        products = [candidate.product.model_copy(deep=True) for candidate in selected]
        reasons = {
            candidate.product.product_id: candidate.reasons for candidate in selected
        }
        confidence = self._confidence(selected)
        output = RecommendationOutput(
            products=products,
            ranking_reasons=reasons,
            strategy=RecommendationStrategy.RULE_BASED_DEMO,
            filtered_count=filtered_count,
            confidence=confidence,
        )
        return AgentResult(
            agent_name=self.name,
            success=True,
            confidence=output.confidence,
            data=output.model_dump(mode="json"),
        )

    @staticmethod
    def _prepare_candidates(
        request: RecommendationInput,
    ) -> tuple[list[_Candidate], int]:
        """Deduplicate, remove out-of-stock items, and score remaining items."""
        filtered_count = 0
        seen_product_ids: set[str] = set()
        prepared: list[_Candidate] = []

        for product in request.candidate_products:
            if product.product_id in seen_product_ids:
                filtered_count += 1
                continue
            seen_product_ids.add(product.product_id)

            if product.stock <= 0:
                filtered_count += 1
                continue

            score, reasons = RecommendationAgent._base_score(product, request)
            prepared.append(_Candidate(product=product, base_score=score, reasons=reasons))
        return prepared, filtered_count

    @staticmethod
    def _base_score(
        product: Product,
        request: RecommendationInput,
    ) -> tuple[int, list[RankingReason]]:
        """Calculate deterministic rule score and structured reasons."""
        score = 0
        reasons: list[RankingReason] = []
        profile = request.user_profile

        preferred_categories = {
            category.casefold() for category in profile.preferred_categories
        }
        if product.category.casefold() in preferred_categories:
            score += 30
            reasons.append(
                RankingReason(
                    code=RecommendationReasonCode.CATEGORY_MATCH,
                    message=f"matches preferred category {product.category}",
                )
            )

        price_range = profile.price_range
        above_min = product.price >= price_range.min_price
        below_max = (
            price_range.max_price is None or product.price <= price_range.max_price
        )
        if above_min and below_max:
            score += 15
            reasons.append(
                RankingReason(
                    code=RecommendationReasonCode.WITHIN_PRICE_RANGE,
                    message="price is within the inferred user price range",
                )
            )

        if product.stock > 0:
            score += 5
            reasons.append(
                RankingReason(
                    code=RecommendationReasonCode.IN_STOCK,
                    message="product is currently in stock",
                )
            )

        interests = {interest.casefold() for interest in profile.recent_interests}
        matched_tags = [tag for tag in product.tags if tag.casefold() in interests]
        if matched_tags:
            score += 20
            reasons.append(
                RankingReason(
                    code=RecommendationReasonCode.TAG_MATCH,
                    message=f"matches interests via tags: {', '.join(matched_tags)}",
                )
            )

        semantic_score = request.retrieval_scores.get(product.product_id, 0.0)
        if semantic_score > 0:
            score += max(1, round(semantic_score * 10))
            reasons.append(
                RankingReason(
                    code=RecommendationReasonCode.SEMANTIC_MATCH,
                    message=f"semantic retrieval score {semantic_score:.3f}",
                )
            )

        return score, reasons

    @staticmethod
    def _select_with_diversity(
        candidates: list[_Candidate],
        num_items: int,
    ) -> list[_Candidate]:
        """Greedily select candidates with a category cap and diversity bonus."""
        remaining = list(candidates)
        selected: list[_Candidate] = []
        selected_categories: set[str] = set()
        category_counts: dict[str, int] = {}

        while len(selected) < num_items and remaining:
            eligible = [
                candidate
                for candidate in remaining
                if category_counts.get(candidate.product.category, 0) < _MAX_PER_CATEGORY
            ]
            if not eligible:
                break

            eligible.sort(
                key=lambda candidate: (
                    -(
                        candidate.base_score
                        + (
                            _DIVERSITY_BONUS
                            if candidate.product.category not in selected_categories
                            else 0
                        )
                    ),
                    candidate.product.product_id,
                )
            )
            chosen = eligible[0]
            remaining.remove(chosen)
            category = chosen.product.category
            if category not in selected_categories:
                chosen.reasons.append(
                    RankingReason(
                        code=RecommendationReasonCode.DIVERSITY_BONUS,
                        message="category diversity bonus applied",
                    )
                )
                selected_categories.add(category)
            category_counts[category] = category_counts.get(category, 0) + 1
            selected.append(chosen)
        return selected

    @staticmethod
    def _confidence(selected: list[_Candidate]) -> float:
        """Derive confidence from average rule score, not from an LLM."""
        if not selected:
            return 0.0
        average_score = sum(candidate.base_score for candidate in selected) / len(selected)
        return round(min(1.0, average_score / _MAX_SCORE), 2)
