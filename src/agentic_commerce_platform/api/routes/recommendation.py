"""Recommendation endpoint: a thin HTTP adapter over the service layer."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from agentic_commerce_platform.api.dependencies import get_recommendation_service
from agentic_commerce_platform.api.middleware import get_request_id
from agentic_commerce_platform.domain.models import (
    ErrorResponse,
    RecommendationRequest,
    RecommendationResponse,
)
from agentic_commerce_platform.services.recommendation_service import RecommendationService

__all__ = ["router"]

router = APIRouter(tags=["recommendation"])


@router.post(
    "/recommend",
    response_model=RecommendationResponse,
    summary="Generate a phase-one skeleton recommendation",
    description=(
        "Validates a recommendation request and returns the phase-one skeleton "
        "response. It does not retrieve products or call a real LLM."
    ),
    responses={
        422: {
            "model": ErrorResponse,
            "description": "Request validation failed.",
        },
        500: {
            "model": ErrorResponse,
            "description": "Unexpected server or configuration error.",
        },
        502: {
            "model": ErrorResponse,
            "description": "The demonstration agent failed.",
        },
        503: {
            "model": ErrorResponse,
            "description": "An external dependency is unavailable.",
        },
    },
)
async def recommend(
    payload: RecommendationRequest,
    request: Request,
    service: Annotated[
        RecommendationService,
        Depends(get_recommendation_service),
    ],
) -> RecommendationResponse:
    """Delegate validation-time work and return the service response.

    The route intentionally contains no retrieval, ranking, or agent logic. It
    supplies the middleware-managed request ID and lets exception handlers
    translate failures into the stable error envelope.
    """
    request_id = get_request_id(request)
    return await service.recommend(payload, request_id=request_id)
