"""User profile and behavior endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path
from pydantic import Field

from agentic_commerce_platform.api.dependencies import (
    get_memory_service,
    get_profile_service,
)
from agentic_commerce_platform.domain.agent_models import UserProfileOutput
from agentic_commerce_platform.domain.data_models import BehaviorEvent
from agentic_commerce_platform.domain.enums import BehaviorType
from agentic_commerce_platform.domain.models import ErrorResponse, PlatformModel
from agentic_commerce_platform.services.memory_service import MemoryService
from agentic_commerce_platform.services.profile_service import ProfileService

__all__ = ["BehaviorCreateRequest", "router"]

router = APIRouter(tags=["users"])


class BehaviorCreateRequest(PlatformModel):
    """Behavior event submitted through the HTTP API."""

    behavior_type: BehaviorType
    item_id: str | None = Field(default=None, max_length=64)
    category: str | None = Field(default=None, max_length=100)
    amount: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        max_digits=12,
        decimal_places=2,
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.get(
    "/users/{user_id}/profile",
    response_model=UserProfileOutput,
    summary="Get or build a persisted user profile",
    responses={
        422: {"model": ErrorResponse, "description": "Invalid user ID."},
        500: {"model": ErrorResponse, "description": "Profile processing failed."},
    },
)
async def get_user_profile(
    user_id: Annotated[str, Path(min_length=1, max_length=128)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
) -> UserProfileOutput:
    """Use the profile service's redis/history/persisted/default priority."""
    return await service.get_or_build_profile(user_id)


@router.post(
    "/users/{user_id}/behaviors",
    response_model=BehaviorEvent,
    status_code=201,
    summary="Record a user behavior in history and short-term memory",
    responses={
        422: {"model": ErrorResponse, "description": "Invalid behavior payload."},
        503: {"model": ErrorResponse, "description": "Memory backend unavailable."},
    },
)
async def record_user_behavior(
    user_id: Annotated[str, Path(min_length=1, max_length=128)],
    payload: BehaviorCreateRequest,
    service: Annotated[MemoryService, Depends(get_memory_service)],
) -> BehaviorEvent:
    """Record behavior through MemoryService, never through a client in the route."""
    event = BehaviorEvent(
        user_id=user_id,
        behavior_type=payload.behavior_type,
        item_id=payload.item_id,
        category=payload.category,
        amount=payload.amount,
        metadata=payload.metadata,
    )
    return await service.record_behavior(event)
