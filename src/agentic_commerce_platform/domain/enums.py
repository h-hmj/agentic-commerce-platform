"""Shared domain enumerations."""

from enum import StrEnum

__all__ = [
    "BehaviorType",
    "DataSource",
    "MarketingProvider",
    "MarketingStyle",
    "ProfileSource",
    "RecommendationReasonCode",
    "RecommendationScene",
    "RecommendationStatus",
    "RecommendationStrategy",
    "RetrievalSource",
    "UserSegment",
    "WorkflowStatus",
]


class RecommendationScene(StrEnum):
    """Supported recommendation request scenes.

    The list is deliberately small in phase one. Additional storefront scenes
    can be added when the real recommendation workflow is implemented.
    """

    HOME = "home"
    PRODUCT_DETAIL = "product_detail"
    CART = "cart"
    CHECKOUT = "checkout"


class RecommendationStatus(StrEnum):
    """Lifecycle status of a recommendation response."""

    SKELETON = "skeleton"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class WorkflowStatus(StrEnum):
    """Lifecycle status of the phase-three multi-agent workflow."""

    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"


class UserSegment(StrEnum):
    """Rule-derived user segments supported in phase two."""

    NEW_USER = "new_user"
    ACTIVE = "active"
    PRICE_SENSITIVE = "price_sensitive"
    HIGH_VALUE = "high_value"
    CHURN_RISK = "churn_risk"


class ProfileSource(StrEnum):
    """How a user profile was produced.

    The structured profile is always rule-derived in phase two. A successful
    Mock LLM call may add an explanation, but it never supplies profile facts.
    """

    RULE_BASED = "rule_based"
    MOCK_LLM = "mock_llm"
    RULE_BASED_AND_MOCK_LLM = "rule_based+mock_llm"


class DataSource(StrEnum):
    """Explicit provenance for data returned by a repository."""

    IN_MEMORY_DEMO = "in_memory_demo"
    IN_MEMORY = "in_memory"
    DATABASE = "database"
    REDIS = "redis"
    HYBRID = "hybrid"
    DEFAULT = "default"


class BehaviorType(StrEnum):
    """Supported user behavior event types."""

    VIEW = "view"
    CLICK = "click"
    PURCHASE = "purchase"


class RecommendationStrategy(StrEnum):
    """Ranking strategy exposed by the phase-two recommendation agent."""

    RULE_BASED_DEMO = "rule_based_demo"


class RecommendationReasonCode(StrEnum):
    """Structured reason codes attached to a ranked product."""

    CATEGORY_MATCH = "category_match"
    WITHIN_PRICE_RANGE = "within_price_range"
    IN_STOCK = "in_stock"
    TAG_MATCH = "tag_match"
    SEMANTIC_MATCH = "semantic_match"
    DIVERSITY_BONUS = "diversity_bonus"


class RetrievalSource(StrEnum):
    """Provenance of a retrieval candidate."""

    VECTOR = "vector"
    DATABASE_KEYWORD = "database_keyword"
    IN_MEMORY = "in_memory"
    FALLBACK = "fallback"


class MarketingStyle(StrEnum):
    """Supported phase-two marketing copy styles."""

    WELCOME = "welcome"
    VALUE = "value"
    PREMIUM = "premium"
    ACTIVE = "active"
    RECALL = "recall"


class MarketingProvider(StrEnum):
    """Source of the final marketing copy."""

    MOCK = "mock"
    RULE_BASED = "rule_based"
