"""Application service for the phase-three multi-agent workflow."""

from __future__ import annotations

from agentic_commerce_platform.domain.models import RecommendationRequest
from agentic_commerce_platform.orchestration.models import (
    WorkflowRecommendationResponse,
)
from agentic_commerce_platform.orchestration.supervisor import SupervisorOrchestrator

__all__ = ["WorkflowService"]


class WorkflowService:
    """Thin application service that delegates to the injected supervisor.

    The API route never calls individual agents; all orchestration remains in the
    supervisor and the compiled LangGraph workflow.
    """

    def __init__(self, supervisor: SupervisorOrchestrator) -> None:
        """Store the explicitly injected supervisor."""
        self._supervisor = supervisor

    @property
    def supervisor(self) -> SupervisorOrchestrator:
        """Return the injected supervisor for verification and tests."""
        return self._supervisor

    async def recommend(
        self,
        request: RecommendationRequest,
        *,
        request_id: str | None = None,
    ) -> WorkflowRecommendationResponse:
        """Execute the workflow and return its aggregated response."""
        return await self._supervisor.run(request, request_id=request_id)
