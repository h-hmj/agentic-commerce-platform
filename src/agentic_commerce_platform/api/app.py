"""FastAPI application factory and ASGI entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from agentic_commerce_platform.agents.demo import DemoAgent
from agentic_commerce_platform.api.exception_handlers import register_exception_handlers
from agentic_commerce_platform.api.middleware import install_request_middleware
from agentic_commerce_platform.api.routes import health, recommendation
from agentic_commerce_platform.infrastructure.llm import build_llm_provider
from agentic_commerce_platform.infrastructure.observability.logging import configure_logging
from agentic_commerce_platform.services.recommendation_service import RecommendationService
from agentic_commerce_platform.settings import Settings, get_settings

__all__ = ["app", "create_app"]

logger = logging.getLogger(__name__)

_APP_DESCRIPTION = (
    "Multi-agent e-commerce platform. Phase-two professional agents are available "
    "as independent services; the public recommendation endpoint remains a "
    "phase-one skeleton using an offline mock LLM and returning no real products."
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a FastAPI application with explicit dependency composition.

    Args:
        settings: Optional settings injection for tests and embedding. When
            omitted, cached environment settings are loaded.

    Returns:
        A fully configured FastAPI application.
    """
    resolved_settings = settings if settings is not None else get_settings()
    configure_logging(
        resolved_settings.log_level.value,
        resolved_settings.log_format.value,
    )

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description=_APP_DESCRIPTION,
        # Never let the framework emit debug tracebacks to API clients, even if
        # the DEBUG setting is enabled for a local development workflow.
        debug=False,
    )
    application.state.settings = resolved_settings

    llm_provider = build_llm_provider(resolved_settings)
    demo_agent = DemoAgent(llm_provider)
    application.state.recommendation_service = RecommendationService(
        llm_provider,
        agent=demo_agent,
    )

    register_exception_handlers(application)
    install_request_middleware(application)
    application.include_router(health.router)
    application.include_router(recommendation.router, prefix="/api/v1")

    logger.info("application_initialized")
    return application


app = create_app()
