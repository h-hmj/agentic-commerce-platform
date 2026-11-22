"""Shared domain enumerations."""

from enum import StrEnum

__all__ = ["RecommendationScene", "RecommendationStatus"]


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
    FAILED = "failed"
