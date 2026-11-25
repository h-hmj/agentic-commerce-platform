"""FastAPI application factory and ASGI entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI

from agentic_commerce_platform.agents.catalog_agent import CatalogAgent
from agentic_commerce_platform.agents.demo import DemoAgent
from agentic_commerce_platform.agents.inventory_agent import InventoryAgent
from agentic_commerce_platform.agents.marketing_agent import MarketingAgent
from agentic_commerce_platform.agents.profile_agent import UserProfileAgent
from agentic_commerce_platform.agents.recommendation_agent import RecommendationAgent
from agentic_commerce_platform.api.exception_handlers import register_exception_handlers
from agentic_commerce_platform.api.middleware import install_request_middleware
from agentic_commerce_platform.api.routes import health, recommendation
from agentic_commerce_platform.infrastructure.data import (
    InMemoryCatalogRepository,
    InMemoryInventoryRepository,
    InMemoryUserBehaviorRepository,
)
from agentic_commerce_platform.infrastructure.llm import build_llm_provider
from agentic_commerce_platform.infrastructure.observability.logging import configure_logging
from agentic_commerce_platform.orchestration.supervisor import (
    SupervisorOrchestrator,
    WorkflowRepositories,
)
from agentic_commerce_platform.services.recommendation_service import RecommendationService
from agentic_commerce_platform.services.workflow_service import WorkflowService
from agentic_commerce_platform.settings import Settings, get_settings

__all__ = ["app", "create_app"]

logger = logging.getLogger(__name__)

_APP_DESCRIPTION = (
    "Multi-agent e-commerce platform. The phase-three workflow runs five "
    "professional agents through LangGraph using phase-2 in-memory demo data and "
    "an offline MockLLMProvider. The original recommendation endpoint remains a "
    "phase-one skeleton; the workflow endpoint is explicitly a demo."
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

    # Phase-one API remains available for compatibility.
    demo_agent = DemoAgent(llm_provider)
    application.state.recommendation_service = RecommendationService(
        llm_provider,
        agent=demo_agent,
    )

    # Phase-three composition root: every professional agent is explicitly
    # constructed and injected into the Supervisor. No hidden global agents exist.
    behavior_repository = InMemoryUserBehaviorRepository()
    catalog_repository = InMemoryCatalogRepository()
    inventory_repository = InMemoryInventoryRepository()

    profile_agent = UserProfileAgent(behavior_repository, llm_provider)
    catalog_agent = CatalogAgent(catalog_repository, llm_provider)
    recommendation_agent = RecommendationAgent(llm_provider)
    inventory_agent = InventoryAgent(inventory_repository, llm_provider)
    marketing_agent = MarketingAgent(llm_provider)

    supervisor = SupervisorOrchestrator(
        profile_agent=profile_agent,
        catalog_agent=catalog_agent,
        recommendation_agent=recommendation_agent,
        inventory_agent=inventory_agent,
        marketing_agent=marketing_agent,
        repositories=WorkflowRepositories(
            user_behavior=behavior_repository,
            catalog=catalog_repository,
            inventory=inventory_repository,
        ),
        llm_provider=llm_provider,
        settings=resolved_settings,
        logger_instance=logger,
    )
    application.state.workflow_service = WorkflowService(supervisor)

    register_exception_handlers(application)
    install_request_middleware(application)
    application.include_router(health.router)
    application.include_router(recommendation.router, prefix="/api/v1")

    logger.info("application_initialized")
    return application


app = create_app()
