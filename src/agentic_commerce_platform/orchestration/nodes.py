"""LangGraph node implementations for the phase-three recommendation workflow.

Nodes contain orchestration only. Business rules remain inside the five
professional agents; repositories are reached through those injected agents.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.agents.catalog_agent import CatalogAgent
from agentic_commerce_platform.agents.inventory_agent import InventoryAgent
from agentic_commerce_platform.agents.marketing_agent import MarketingAgent
from agentic_commerce_platform.agents.profile_agent import UserProfileAgent
from agentic_commerce_platform.agents.recommendation_agent import RecommendationAgent
from agentic_commerce_platform.domain.agent_models import (
    CatalogInput,
    CatalogOutput,
    InventoryInput,
    InventoryOutput,
    MarketingInput,
    MarketingOutput,
    PriceRange,
    RecommendationInput,
    RecommendationOutput,
    UserProfileInput,
    UserProfileOutput,
)
from agentic_commerce_platform.domain.enums import (
    DataSource,
    ProfileSource,
    UserSegment,
    WorkflowStatus,
)
from agentic_commerce_platform.domain.models import (
    AgentResult,
    Product,
    RecommendationContext,
)
from agentic_commerce_platform.orchestration.state import RecommendationWorkflowState

__all__ = ["WorkflowNodes"]

logger = logging.getLogger(__name__)

_OutputT = TypeVar("_OutputT", bound=BaseModel)
_LOW_STOCK_THRESHOLD = 3


def _utc_now() -> str:
    """Return an ISO-8601 UTC timestamp for workflow observability."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _safe_error(exc: BaseException) -> str:
    """Render a bounded internal error string for AgentResult only."""
    message = str(exc).strip()
    rendered = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
    return rendered[:1000]


class WorkflowNodes:
    """Node functions bound to injected professional agents.

    Nodes never create agents, repositories, or network clients. Each node
    returns a partial state update; LangGraph handles the explicit state merge.
    """

    def __init__(
        self,
        *,
        profile_agent: UserProfileAgent,
        catalog_agent: CatalogAgent,
        recommendation_agent: RecommendationAgent,
        inventory_agent: InventoryAgent,
        marketing_agent: MarketingAgent,
    ) -> None:
        """Store the five explicitly injected agents."""
        self._profile_agent = profile_agent
        self._catalog_agent = catalog_agent
        self._recommendation_agent = recommendation_agent
        self._inventory_agent = inventory_agent
        self._marketing_agent = marketing_agent

    @asynccontextmanager
    async def _node_span(
        self,
        node_name: str,
        state: RecommendationWorkflowState,
        *,
        agent_name: str | None = None,
    ) -> AsyncIterator[None]:
        """Log node start/completion and duration without sensitive payloads."""
        started_at = time.perf_counter()
        extra: dict[str, Any] = {
            "request_id": state.get("request_id", "-") or "-",
            "current_node": node_name,
            "workflow_status": _status_value(state.get("workflow_status")),
        }
        if agent_name:
            extra["agent_name"] = agent_name
        logger.info("workflow_node_started", extra=extra)
        try:
            yield
        except Exception:
            logger.exception(
                "workflow_node_failed",
                extra={
                    **extra,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
                },
            )
            raise
        else:
            logger.info(
                "workflow_node_completed",
                extra={
                    **extra,
                    "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
                },
            )

    async def initialize_request_node(
        self,
        state: RecommendationWorkflowState,
    ) -> RecommendationWorkflowState:
        """Generate/confirm request ID and initialize workflow observability."""
        async with self._node_span("initialize_request", state):
            request_id = str(state.get("request_id") or "").strip() or uuid4().hex
            return RecommendationWorkflowState(
                request_id=request_id,
                started_at=_utc_now(),
                started_at_monotonic=time.perf_counter(),
                completed_at=None,
                total_latency_ms=0.0,
                current_node="initialize_request",
                workflow_status=WorkflowStatus.RUNNING,
                failed_stage=None,
                final_product_count=0,
                agent_results={},
                errors=[],
                warnings=[],
            )

    async def user_profile_node(
        self,
        state: RecommendationWorkflowState,
    ) -> RecommendationWorkflowState:
        """Run UserProfileAgent and retain either a profile or default fallback."""
        async with self._node_span(
            "user_profile",
            state,
            agent_name=self._profile_agent.name,
        ):
            request = UserProfileInput(user_id=state["user_id"])
            result, output, failure = await self._invoke_agent(
                self._profile_agent,
                request,
                UserProfileOutput,
            )
            updates = RecommendationWorkflowState(
                user_profile_input=request,
                agent_results={result.agent_name: result},
            )
            if failure or output is None:
                updates["user_profile"] = self._default_profile(state["user_id"])
                updates["errors"] = [self._failure_code("user_profile", failure)]
                updates["warnings"] = ["user_profile_fallback_default"]
            else:
                updates["user_profile"] = output
                if output.warnings:
                    updates["warnings"] = [
                        f"user_profile_{warning}" for warning in output.warnings
                    ]
            return updates

    async def catalog_node(
        self,
        state: RecommendationWorkflowState,
    ) -> RecommendationWorkflowState:
        """Run CatalogAgent using validated request context as filters."""
        async with self._node_span(
            "catalog",
            state,
            agent_name=self._catalog_agent.name,
        ):
            context = self._context(state)
            request = CatalogInput(
                query=" ".join(context.keywords),
                category=context.category,
                limit=max(10, min(50, state.get("num_items", 10) * 3)),
            )
            result, output, failure = await self._invoke_agent(
                self._catalog_agent,
                request,
                CatalogOutput,
            )
            updates = RecommendationWorkflowState(
                catalog_input=request,
                agent_results={result.agent_name: result},
            )
            if failure or output is None:
                updates["candidate_products"] = []
                updates["errors"] = [self._failure_code("catalog", failure)]
                updates["warnings"] = ["catalog_failure_products_withheld"]
                updates["failed_stage"] = "catalog"
            else:
                updates["candidate_products"] = output.products
                if not output.products:
                    updates["warnings"] = ["catalog_returned_no_products"]
            return updates

    async def recommendation_node(
        self,
        state: RecommendationWorkflowState,
    ) -> RecommendationWorkflowState:
        """Run RecommendationAgent after profile/catalog parallel join."""
        async with self._node_span(
            "recommendation",
            state,
            agent_name=self._recommendation_agent.name,
        ):
            candidates = state.get("candidate_products", [])
            profile = state.get("user_profile")
            if profile is None:
                profile = self._default_profile(state["user_id"])
                fallback_warning = ["user_profile_missing_default_used"]
            else:
                fallback_warning = []

            updates = RecommendationWorkflowState(
                current_node="recommendation",
                recommendation_input=None,
                ranked_products=[],
                warnings=fallback_warning,
            )
            if state.get("failed_stage") == "catalog" or not candidates:
                updates["warnings"] = [
                    *fallback_warning,
                    "no_candidate_products",
                ]
                return updates

            request = RecommendationInput(
                user_profile=profile,
                candidate_products=candidates,
                num_items=state.get("num_items", 5),
            )
            updates["recommendation_input"] = request
            result, output, failure = await self._invoke_agent(
                self._recommendation_agent,
                request,
                RecommendationOutput,
            )
            updates["agent_results"] = {result.agent_name: result}
            if failure or output is None:
                updates["errors"] = [self._failure_code("recommendation", failure)]
                updates["warnings"] = [
                    *fallback_warning,
                    "recommendation_failure_products_withheld",
                ]
                updates["failed_stage"] = "recommendation"
            else:
                updates["ranked_products"] = output.products
                if not output.products:
                    updates["warnings"] = [
                        *fallback_warning,
                        "recommendation_returned_no_products",
                    ]
            return updates

    async def inventory_node(
        self,
        state: RecommendationWorkflowState,
    ) -> RecommendationWorkflowState:
        """Run InventoryAgent and never assume stock when lookup fails."""
        async with self._node_span(
            "inventory",
            state,
            agent_name=self._inventory_agent.name,
        ):
            ranked_products = state.get("ranked_products", [])
            updates = RecommendationWorkflowState(
                current_node="inventory",
                inventory_input=None,
                available_products=[],
                unavailable_products=[],
                inventory_alerts=[],
            )
            if not ranked_products:
                updates["warnings"] = ["inventory_skipped_no_ranked_products"]
                return updates

            request = InventoryInput(
                products=ranked_products,
                low_stock_threshold=_LOW_STOCK_THRESHOLD,
            )
            updates["inventory_input"] = request
            result, output, failure = await self._invoke_agent(
                self._inventory_agent,
                request,
                InventoryOutput,
            )
            updates["agent_results"] = {result.agent_name: result}
            if failure or output is None:
                updates["errors"] = [self._failure_code("inventory", failure)]
                updates["warnings"] = ["inventory_failure_products_withheld"]
                updates["failed_stage"] = "inventory"
            else:
                updates["available_products"] = output.available_products
                updates["unavailable_products"] = output.unavailable_products
                updates["inventory_alerts"] = output.low_stock_alerts
            return updates

    async def inventory_filter_node(
        self,
        state: RecommendationWorkflowState,
    ) -> RecommendationWorkflowState:
        """Keep only inventory-approved products in recommendation order."""
        async with self._node_span("inventory_filter", state):
            if state.get("failed_stage") == "inventory":
                return RecommendationWorkflowState(
                    current_node="inventory_filter",
                    available_products=[],
                    warnings=["inventory_failure_products_withheld"],
                )

            available_ids = {
                product.product_id for product in state.get("available_products", [])
            }
            ordered_available = [
                product
                for product in state.get("ranked_products", [])
                if product.product_id in available_ids
            ]
            updates = RecommendationWorkflowState(
                current_node="inventory_filter",
                available_products=ordered_available,
                final_product_count=len(ordered_available),
            )
            if not ordered_available:
                updates["warnings"] = ["no_available_products"]
            return updates

    async def marketing_node(
        self,
        state: RecommendationWorkflowState,
    ) -> RecommendationWorkflowState:
        """Run MarketingAgent only for inventory-approved final products."""
        async with self._node_span(
            "marketing",
            state,
            agent_name=self._marketing_agent.name,
        ):
            products = state.get("available_products", [])
            updates = RecommendationWorkflowState(
                current_node="marketing",
                marketing_input=None,
                marketing_copies=[],
            )
            if not products:
                updates["warnings"] = ["marketing_skipped_no_available_products"]
                return updates

            profile = state.get("user_profile")
            if profile is None:
                profile = self._default_profile(state["user_id"])
                warnings = ["user_profile_missing_default_used"]
            else:
                warnings = []
            request = MarketingInput(user_profile=profile, products=products)
            updates["marketing_input"] = request
            result, output, failure = await self._invoke_agent(
                self._marketing_agent,
                request,
                MarketingOutput,
            )
            updates["agent_results"] = {result.agent_name: result}
            if failure or output is None:
                updates["errors"] = [self._failure_code("marketing", failure)]
                updates["warnings"] = [
                    *warnings,
                    "marketing_copies_unavailable",
                ]
                return updates

            final_ids = {product.product_id for product in products}
            valid_copies = [
                copy for copy in output.copies if copy.product_id in final_ids
            ]
            updates["marketing_copies"] = valid_copies
            if warnings:
                updates["warnings"] = warnings
            if len(valid_copies) != len(output.copies):
                updates["errors"] = ["marketing_copy_product_mismatch"]
                updates["warnings"] = [
                    *warnings,
                    "marketing_copies_filtered_to_final_products",
                ]
            return updates

    async def aggregate_node(
        self,
        state: RecommendationWorkflowState,
    ) -> RecommendationWorkflowState:
        """Finalize latency, status, and aggregated product counts."""
        async with self._node_span("aggregate", state):
            completed_at = _utc_now()
            started_monotonic = state.get("started_at_monotonic", 0.0)
            total_latency_ms = (
                max(0.0, (time.perf_counter() - started_monotonic) * 1000.0)
                if started_monotonic
                else 0.0
            )
            products = state.get("available_products", [])
            errors = state.get("errors", [])
            warnings = state.get("warnings", [])
            workflow_status = self._final_status(products, errors, warnings)
            final_state = RecommendationWorkflowState(
                completed_at=completed_at,
                total_latency_ms=total_latency_ms,
                current_node="aggregate",
                workflow_status=workflow_status,
                available_products=products,
                unavailable_products=state.get("unavailable_products", []),
                inventory_alerts=state.get("inventory_alerts", []),
                marketing_copies=state.get("marketing_copies", []),
                final_product_count=len(products),
            )
            logger.info(
                "workflow_aggregated",
                extra={
                    "request_id": state.get("request_id", "-"),
                    "current_node": "aggregate",
                    "workflow_status": workflow_status.value,
                    "final_product_count": len(products),
                    "duration_ms": round(total_latency_ms, 2),
                    "error_code": errors[0] if errors else None,
                },
            )
            return final_state

    async def _invoke_agent(
        self,
        agent: BaseAgent,
        request: BaseModel,
        output_type: type[_OutputT],
    ) -> tuple[AgentResult, _OutputT | None, str]:
        """Invoke an agent and validate its structured output.

        Returns:
            ``(agent_result, validated_output_or_none, failure_kind)`` where
            ``failure_kind`` is ``"agent_failed"`` or ``"invalid_output"``.
            The caller decides the safe workflow fallback.
        """
        try:
            result = await agent.run(request=request)
        except Exception as exc:
            logger.exception(
                "workflow_agent_raised",
                extra={"agent_name": agent.name},
            )
            result = AgentResult(
                agent_name=agent.name,
                success=False,
                latency_ms=0.0,
                error=_safe_error(exc),
                data={},
            )
            return result, None, "agent_failed"

        if not result.success:
            return result, None, "agent_failed"

        try:
            return result, output_type.model_validate(result.data), ""
        except ValidationError:
            logger.exception(
                "workflow_agent_output_invalid",
                extra={"agent_name": agent.name},
            )
            return result, None, "invalid_output"

    @staticmethod
    def _context(state: RecommendationWorkflowState) -> RecommendationContext:
        """Return a validated context from state, accepting dict serialization."""
        raw_context = state.get("context")
        if isinstance(raw_context, RecommendationContext):
            return raw_context
        return RecommendationContext.model_validate(raw_context or {})

    @staticmethod
    def _failure_code(stage: str, failure: str) -> str:
        """Map an internal failure kind to a stable, safe public error code."""
        if failure == "invalid_output":
            return f"{stage}_output_invalid"
        return f"{stage}_agent_failed"

    @staticmethod
    def _default_profile(user_id: str) -> UserProfileOutput:
        """Build an explicit, low-confidence fallback after profile failure."""
        return UserProfileOutput(
            user_id=user_id,
            segments=[UserSegment.NEW_USER],
            preferred_categories=[],
            price_range=PriceRange(),
            recent_interests=[],
            confidence=0.0,
            profile_source=ProfileSource.RULE_BASED,
            data_source=DataSource.IN_MEMORY_DEMO,
            explanation=None,
            warnings=["user_profile_fallback_default"],
        )

    @staticmethod
    def _final_status(
        products: list[Product],
        errors: list[str],
        warnings: list[str],
    ) -> WorkflowStatus:
        """Classify final state without confusing empty results with crashes."""
        if not products:
            return WorkflowStatus.FAILED if errors else WorkflowStatus.PARTIAL_SUCCESS
        if errors or warnings:
            return WorkflowStatus.PARTIAL_SUCCESS
        return WorkflowStatus.SUCCESS


def _status_value(value: WorkflowStatus | str | None) -> str:
    """Render a workflow status for log extras."""
    if isinstance(value, WorkflowStatus):
        return value.value
    return str(value or WorkflowStatus.RUNNING.value)
