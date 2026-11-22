"""Domain models, enums, and project-level exceptions."""

from ecommerce_platform.domain.enums import RecommendationScene, RecommendationStatus
from ecommerce_platform.domain.errors import (
    AgentExecutionError,
    ConfigurationError,
    EcommercePlatformError,
    ExternalServiceError,
)
from ecommerce_platform.domain.models import (
    AgentResult,
    ErrorDetail,
    ErrorResponse,
    Product,
    RecommendationContext,
    RecommendationRequest,
    RecommendationResponse,
)

__all__ = [
    "AgentExecutionError",
    "AgentResult",
    "ConfigurationError",
    "EcommercePlatformError",
    "ErrorDetail",
    "ErrorResponse",
    "ExternalServiceError",
    "Product",
    "RecommendationContext",
    "RecommendationRequest",
    "RecommendationResponse",
    "RecommendationScene",
    "RecommendationStatus",
]
