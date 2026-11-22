"""Domain models, enums, and project-level exceptions."""

from agentic_commerce_platform.domain.enums import RecommendationScene, RecommendationStatus
from agentic_commerce_platform.domain.errors import (
    AgentExecutionError,
    ConfigurationError,
    EcommercePlatformError,
    ExternalServiceError,
)
from agentic_commerce_platform.domain.models import (
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
