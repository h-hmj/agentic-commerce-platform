"""FastAPI application factory and ASGI entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from agentic_commerce_platform.agents.demo import DemoAgent
from agentic_commerce_platform.api.composition import (
    Phase4Resources,
    build_phase4_resources,
)
from agentic_commerce_platform.api.exception_handlers import register_exception_handlers
from agentic_commerce_platform.api.middleware import install_request_middleware
from agentic_commerce_platform.api.routes import catalog, health, recommendation, retrieval, users
from agentic_commerce_platform.infrastructure.llm import build_llm_provider
from agentic_commerce_platform.infrastructure.observability.logging import configure_logging
from agentic_commerce_platform.services.recommendation_service import RecommendationService
from agentic_commerce_platform.settings import Settings, get_settings

__all__ = ["app", "create_app"]

logger = logging.getLogger(__name__)

_APP_DESCRIPTION = (
    "Multi-agent e-commerce platform with SQLite persistence, optional Redis "
    "memory, deterministic local RAG, and a LangGraph Supervisor workflow. "
    "The phase-one recommendation endpoint remains a compatibility skeleton; "
    "the workflow and phase-four endpoints expose explicit demo/real data sources."
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a FastAPI application with explicit adapter composition."""
    resolved_settings = settings if settings is not None else get_settings()
    configure_logging(
        resolved_settings.log_level.value,
        resolved_settings.log_format.value,
    )

    llm_provider = build_llm_provider(resolved_settings)
    resources: Phase4Resources = build_phase4_resources(
        resolved_settings,
        llm_provider,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Yield the app, then release memory/database resources."""
        yield
        try:
            await resources.memory_store.close()
        except Exception:
            logger.warning("memory_store_shutdown_failed", exc_info=True)
        if resources.database is not None:
            resources.database.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        description=_APP_DESCRIPTION,
        debug=False,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings

    # Phase-one endpoint remains unchanged.
    demo_agent = DemoAgent(llm_provider)
    application.state.recommendation_service = RecommendationService(
        llm_provider,
        agent=demo_agent,
    )

    application.state.phase4_resources = resources
    application.state.workflow_service = resources.workflow_service
    application.state.catalog_service = resources.catalog_service
    application.state.profile_service = resources.profile_service
    application.state.memory_service = resources.memory_service
    application.state.retrieval_service = resources.retrieval_service

    register_exception_handlers(application)
    install_request_middleware(application)
    application.include_router(health.router)
    application.include_router(recommendation.router, prefix="/api/v1")
    application.include_router(catalog.router, prefix="/api/v1")
    application.include_router(users.router, prefix="/api/v1")
    application.include_router(retrieval.router, prefix="/api/v1")

    logger.info("application_initialized")
    return application


app = create_app()
