"""Supervisor orchestration for the phase-three LangGraph workflow."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from agentic_commerce_platform.agents.catalog_agent import CatalogAgent
from agentic_commerce_platform.agents.inventory_agent import InventoryAgent
from agentic_commerce_platform.agents.marketing_agent import MarketingAgent
from agentic_commerce_platform.agents.profile_agent import UserProfileAgent
from agentic_commerce_platform.agents.recommendation_agent import RecommendationAgent
from agentic_commerce_platform.domain.enums import (
    DataSource,
    RecommendationStatus,
    WorkflowStatus,
)
from agentic_commerce_platform.domain.models import RecommendationRequest
from agentic_commerce_platform.domain.ports import (
    CatalogRepository,
    InventoryRepository,
    UserBehaviorRepository,
)
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider
from agentic_commerce_platform.infrastructure.observability.logging import (
    request_log_context,
)
from agentic_commerce_platform.orchestration.graph import build_recommendation_graph
from agentic_commerce_platform.orchestration.models import (
    WorkflowRecommendationResponse,
)
from agentic_commerce_platform.orchestration.nodes import WorkflowNodes
from agentic_commerce_platform.orchestration.state import (
    RecommendationWorkflowState,
    build_initial_workflow_state,
    merge_unique_strings,
)
from agentic_commerce_platform.settings import Settings

__all__ = ["SupervisorOrchestrator", "WorkflowRepositories"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkflowRepositories:
    """Repository dependencies injected into the workflow composition.

    The repositories are bound to the injected agents. Keeping them in the
    supervisor's explicit dependency bundle makes the data source replaceable and
    auditable without allowing agents or nodes to create hidden clients.
    """

    user_behavior: UserBehaviorRepository
    catalog: CatalogRepository
    inventory: InventoryRepository


class SupervisorOrchestrator:
    """Coordinate the LangGraph workflow without owning business rules.

    The supervisor receives five concrete agents and their repository/provider
    dependencies, builds the graph from injected node agents, executes it, and
    converts the final typed state into a public response. It does not implement
    profiling, catalog search, ranking, inventory, or copywriting rules.
    """

    def __init__(
        self,
        *,
        profile_agent: UserProfileAgent,
        catalog_agent: CatalogAgent,
        recommendation_agent: RecommendationAgent,
        inventory_agent: InventoryAgent,
        marketing_agent: MarketingAgent,
        repositories: WorkflowRepositories,
        llm_provider: LLMProvider,
        settings: Settings,
        logger_instance: logging.Logger | None = None,
    ) -> None:
        """Initialize the supervisor and compile its graph from injected agents."""
        self._profile_agent = profile_agent
        self._catalog_agent = catalog_agent
        self._recommendation_agent = recommendation_agent
        self._inventory_agent = inventory_agent
        self._marketing_agent = marketing_agent
        self._repositories = repositories
        self._llm_provider = llm_provider
        self._settings = settings
        self._logger = logger_instance or logger
        self._nodes = WorkflowNodes(
            profile_agent=profile_agent,
            catalog_agent=catalog_agent,
            recommendation_agent=recommendation_agent,
            inventory_agent=inventory_agent,
            marketing_agent=marketing_agent,
        )
        self._graph = build_recommendation_graph(self._nodes)

    @property
    def agents(self) -> dict[str, object]:
        """Return the five explicitly injected agents for verification."""
        return {
            self._profile_agent.name: self._profile_agent,
            self._catalog_agent.name: self._catalog_agent,
            self._recommendation_agent.name: self._recommendation_agent,
            self._inventory_agent.name: self._inventory_agent,
            self._marketing_agent.name: self._marketing_agent,
        }

    @property
    def repositories(self) -> WorkflowRepositories:
        """Return the injected repository bundle (read-only visibility)."""
        return self._repositories

    @property
    def llm_provider(self) -> LLMProvider:
        """Return the injected LLM provider."""
        return self._llm_provider

    @property
    def settings(self) -> Settings:
        """Return the injected settings object."""
        return self._settings

    @property
    def graph(self) -> object:
        """Return the compiled LangGraph graph for structure inspection."""
        return self._graph

    async def run_workflow(
        self,
        request: RecommendationRequest,
        *,
        request_id: str | None = None,
    ) -> RecommendationWorkflowState:
        """Execute the LangGraph workflow and return its final typed state.

        Technical failures escape only as a failed workflow state; their full
        stack remains in server logs and is never returned through the API.
        """
        effective_request_id = (
            request_id.strip() if request_id and request_id.strip() else uuid4().hex
        )
        initial_state = build_initial_workflow_state(request, effective_request_id)
        initial_state["data_source"] = self._settings_data_source()
        started_at = time.perf_counter()

        with request_log_context(effective_request_id):
            self._logger.info(
                "workflow_started",
                extra={
                    "workflow_status": WorkflowStatus.RUNNING.value,
                    "scene": request.scene.value,
                    "num_items": request.num_items,
                },
            )
            last_state: RecommendationWorkflowState = initial_state
            try:
                # Stream full state snapshots instead of only awaiting a final
                # dict. If a graph-level exception occurs, the most recent
                # successful snapshot still contains prior nodes' agent results,
                # errors, warnings, and any products produced before the crash.
                async for snapshot in self._graph.astream(
                    initial_state,
                    stream_mode="values",
                ):
                    if not isinstance(snapshot, dict):
                        raise TypeError(
                            "LangGraph workflow yielded a non-dict state snapshot"
                        )
                    last_state = cast(RecommendationWorkflowState, snapshot)
                final_state = last_state
            except Exception:
                self._logger.exception(
                    "workflow_execution_failed",
                    extra={"workflow_status": WorkflowStatus.FAILED.value},
                )
                final_state = self._failed_state(
                    request,
                    effective_request_id,
                    started_at,
                    previous_state=last_state,
                    data_source=self._settings_data_source(),
                )
            final_status = _status_value(final_state.get("workflow_status"))
            final_count = len(final_state.get("available_products", []))
            self._logger.info(
                "workflow_completed",
                extra={
                    "workflow_status": final_status,
                    "final_product_count": final_count,
                    "duration_ms": round(
                        (time.perf_counter() - started_at) * 1000.0, 2
                    ),
                },
            )
            return cast(RecommendationWorkflowState, final_state)

    async def run(
        self,
        request: RecommendationRequest,
        *,
        request_id: str | None = None,
    ) -> WorkflowRecommendationResponse:
        """Execute the workflow and return the aggregated public response."""
        state = await self.run_workflow(request, request_id=request_id)
        return self._to_response(state)

    def _to_response(
        self,
        state: RecommendationWorkflowState,
    ) -> WorkflowRecommendationResponse:
        """Aggregate a final state into the stable workflow response contract."""
        workflow_status = _workflow_status(state.get("workflow_status"))
        products = state.get("available_products", [])
        final_ids = {product.product_id for product in products}
        copies = [
            copy
            for copy in state.get("marketing_copies", [])
            if copy.product_id in final_ids
        ]
        status = {
            WorkflowStatus.SUCCESS: RecommendationStatus.SUCCESS,
            WorkflowStatus.PARTIAL_SUCCESS: RecommendationStatus.PARTIAL_SUCCESS,
            WorkflowStatus.FAILED: RecommendationStatus.FAILED,
            WorkflowStatus.RUNNING: RecommendationStatus.FAILED,
        }[workflow_status]
        messages = [
            "结果使用配置的数据适配器与 MockLLMProvider；不是真实线上推荐。"
        ]
        sources = sorted(
            {
                source
                for source in state.get("retrieval_sources", {}).values()
                if source
            }
        )
        data_source = (
            DataSource.DATABASE
            if self._settings.use_real_adapters
            else DataSource.IN_MEMORY_DEMO
        )
        return WorkflowRecommendationResponse(
            request_id=state["request_id"],
            user_id=state["user_id"],
            status=status,
            workflow_status=workflow_status,
            products=products,
            marketing_copies=copies,
            unavailable_products=state.get("unavailable_products", []),
            inventory_alerts=state.get("inventory_alerts", []),
            agent_results=state.get("agent_results", {}),
            errors=state.get("errors", []),
            warnings=state.get("warnings", []),
            total_latency_ms=state.get("total_latency_ms", 0.0),
            data_source=data_source,
            retrieval_source=",".join(sources) if sources else None,
            embedding_provider=self._settings.embedding_provider,
            memory_source=state.get("memory_source"),
            llm_provider=self._settings.llm_provider,
            messages=messages,
        )

    def _settings_data_source(self) -> str:
        """Return the configured adapter provenance marker."""
        return "database" if self._settings.use_real_adapters else "in_memory_demo"

    def _failed_state(
        self,
        request: RecommendationRequest,
        request_id: str,
        started_at: float,
        *,
        previous_state: RecommendationWorkflowState | None = None,
        data_source: str,
    ) -> RecommendationWorkflowState:
        """Preserve the last successful graph snapshot on a graph-level failure."""
        now = datetime.now(UTC).isoformat(timespec="milliseconds")
        preserved = dict(previous_state or {})
        products = list(preserved.get("available_products", []))
        workflow_status = (
            WorkflowStatus.PARTIAL_SUCCESS if products else WorkflowStatus.FAILED
        )
        preserved.update(
            {
                "request_id": request_id,
                "user_id": request.user_id,
                "scene": request.scene.value,
                "num_items": request.num_items,
                "context": request.context,
                "current_node": "workflow",
                "workflow_status": workflow_status,
                "failed_stage": "workflow",
                "started_at": preserved.get("started_at") or now,
                "completed_at": now,
                "total_latency_ms": (time.perf_counter() - started_at) * 1000.0,
                "final_product_count": len(products),
                "agent_results": preserved.get("agent_results", {}),
                "available_products": products,
                "unavailable_products": preserved.get("unavailable_products", []),
                "inventory_alerts": preserved.get("inventory_alerts", []),
                "marketing_copies": preserved.get("marketing_copies", []),
                "data_source": data_source,
                "retrieval_sources": preserved.get("retrieval_sources", {}),
                "retrieval_scores": preserved.get("retrieval_scores", {}),
                "profile_source": preserved.get("profile_source"),
                "memory_source": preserved.get("memory_source"),
                "errors": merge_unique_strings(
                    preserved.get("errors", []),
                    ["workflow_execution_failed"],
                ),
                "warnings": preserved.get("warnings", []),
            }
        )
        return RecommendationWorkflowState(**preserved)


def _workflow_status(value: WorkflowStatus | str | None) -> WorkflowStatus:
    """Normalize a state status into the workflow enum."""
    if isinstance(value, WorkflowStatus):
        return value
    if isinstance(value, str):
        try:
            return WorkflowStatus(value)
        except ValueError:
            return WorkflowStatus.FAILED
    return WorkflowStatus.FAILED


def _status_value(value: WorkflowStatus | str | None) -> str:
    """Render a status for logging."""
    return _workflow_status(value).value
