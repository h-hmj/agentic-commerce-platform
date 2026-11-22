"""Liveness/readiness-style health endpoint for phase one."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ecommerce_platform.api.dependencies import get_app_settings
from ecommerce_platform.settings import Settings

__all__ = ["HealthResponse", "router"]

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    """Public health-check payload."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy"] = Field(description="Current health status.")
    app_name: str = Field(description="Configured application name.")
    version: str = Field(description="Configured application version.")
    environment: str = Field(description="Current runtime environment.")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check application health",
)
async def health(
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> HealthResponse:
    """Return basic process health and build metadata.

    This endpoint intentionally checks only that the application can serve
    requests. It does not probe databases, caches, or LLM providers because
    none are part of phase one.
    """
    return HealthResponse(
        status="healthy",
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env.value,
    )
