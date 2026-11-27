"""Catalog and RAG-aware product search endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from agentic_commerce_platform.api.dependencies import get_catalog_service
from agentic_commerce_platform.domain.agent_models import CatalogInput, CatalogOutput
from agentic_commerce_platform.domain.models import ErrorResponse
from agentic_commerce_platform.services.catalog_service import CatalogService

__all__ = ["router"]

router = APIRouter(tags=["catalog"])


@router.post(
    "/catalog/search",
    response_model=CatalogOutput,
    summary="Search the catalog with structured filters and optional RAG",
    responses={
        422: {"model": ErrorResponse, "description": "Request validation failed."},
        500: {"model": ErrorResponse, "description": "Catalog search failed."},
    },
)
async def search_catalog(
    payload: CatalogInput,
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> CatalogOutput:
    """Delegate catalog search to the single-agent CatalogService."""
    return await service.search_products(payload)
