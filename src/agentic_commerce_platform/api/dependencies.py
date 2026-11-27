"""FastAPI dependency providers for application-scoped objects."""

from __future__ import annotations

from fastapi import Request

from agentic_commerce_platform.domain.errors import ConfigurationError
from agentic_commerce_platform.services.catalog_service import CatalogService
from agentic_commerce_platform.services.memory_service import MemoryService
from agentic_commerce_platform.services.profile_service import ProfileService
from agentic_commerce_platform.services.recommendation_service import RecommendationService
from agentic_commerce_platform.services.retrieval_service import RetrievalService
from agentic_commerce_platform.services.workflow_service import WorkflowService
from agentic_commerce_platform.settings import Settings

__all__ = [
    "get_app_settings",
    "get_catalog_service",
    "get_memory_service",
    "get_profile_service",
    "get_recommendation_service",
    "get_retrieval_service",
    "get_workflow_service",
]


def get_app_settings(request: Request) -> Settings:
    """Return validated settings stored on the ASGI application."""
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise ConfigurationError("Application settings are not configured.")
    return settings


def get_recommendation_service(request: Request) -> RecommendationService:
    """Return the phase-one recommendation skeleton service."""
    service = getattr(request.app.state, "recommendation_service", None)
    if not isinstance(service, RecommendationService):
        raise ConfigurationError("RecommendationService is not configured.")
    return service


def get_workflow_service(request: Request) -> WorkflowService:
    """Return the Supervisor-backed workflow service."""
    service = getattr(request.app.state, "workflow_service", None)
    if not isinstance(service, WorkflowService):
        raise ConfigurationError("WorkflowService is not configured.")
    return service


def get_catalog_service(request: Request) -> CatalogService:
    """Return the catalog/RAG service."""
    service = getattr(request.app.state, "catalog_service", None)
    if not isinstance(service, CatalogService):
        raise ConfigurationError("CatalogService is not configured.")
    return service


def get_profile_service(request: Request) -> ProfileService:
    """Return the profile persistence/memory service."""
    service = getattr(request.app.state, "profile_service", None)
    if not isinstance(service, ProfileService):
        raise ConfigurationError("ProfileService is not configured.")
    return service


def get_memory_service(request: Request) -> MemoryService:
    """Return the behavior/memory service."""
    service = getattr(request.app.state, "memory_service", None)
    if not isinstance(service, MemoryService):
        raise ConfigurationError("MemoryService is not configured.")
    return service


def get_retrieval_service(request: Request) -> RetrievalService:
    """Return the RAG retrieval service."""
    service = getattr(request.app.state, "retrieval_service", None)
    if not isinstance(service, RetrievalService):
        raise ConfigurationError("RetrievalService is not configured.")
    return service
