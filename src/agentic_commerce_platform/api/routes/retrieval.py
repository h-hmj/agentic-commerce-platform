"""Explicit RAG retrieval endpoint."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import Field, model_validator

from agentic_commerce_platform.api.dependencies import get_retrieval_service
from agentic_commerce_platform.domain.data_models import RetrievalResult
from agentic_commerce_platform.domain.models import ErrorResponse, PlatformModel
from agentic_commerce_platform.services.retrieval_service import RetrievalService

__all__ = ["RetrievalSearchRequest", "router"]

router = APIRouter(tags=["retrieval"])


class RetrievalSearchRequest(PlatformModel):
    """Explicit retrieval query and filters."""

    query: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    min_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    max_price: Decimal | None = Field(default=None, ge=Decimal("0"))
    top_k: int = Field(default=8, ge=1, le=50)

    @model_validator(mode="after")
    def validate_price_range(self) -> RetrievalSearchRequest:
        """Reject inverted price bounds."""
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price must not be greater than max_price")
        return self


@router.post(
    "/retrieval/search",
    response_model=RetrievalResult,
    summary="Search RAG candidates with scores and provenance",
    responses={
        422: {"model": ErrorResponse, "description": "Request validation failed."},
        500: {"model": ErrorResponse, "description": "Retrieval failed."},
    },
)
async def search_retrieval(
    payload: RetrievalSearchRequest,
    service: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> RetrievalResult:
    """Delegate vector+filter retrieval to the RAG service."""
    return service.search(
        payload.query,
        category=payload.category,
        min_price=payload.min_price,
        max_price=payload.max_price,
        top_k=payload.top_k,
    )
