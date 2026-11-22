"""FastAPI dependency providers for application-scoped objects."""

from __future__ import annotations

from fastapi import Request

from agentic_commerce_platform.domain.errors import ConfigurationError
from agentic_commerce_platform.services.recommendation_service import RecommendationService
from agentic_commerce_platform.settings import Settings

__all__ = ["get_app_settings", "get_recommendation_service"]


def get_app_settings(request: Request) -> Settings:
    """Return validated settings stored on the ASGI application.

    Raises:
        ConfigurationError: If the application was assembled incorrectly.
    """
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise ConfigurationError("Application settings are not configured.")
    return settings


def get_recommendation_service(request: Request) -> RecommendationService:
    """Return the application-scoped recommendation service.

    Raises:
        ConfigurationError: If the service was not initialized by the app factory.
    """
    service = getattr(request.app.state, "recommendation_service", None)
    if not isinstance(service, RecommendationService):
        raise ConfigurationError("RecommendationService is not configured.")
    return service
