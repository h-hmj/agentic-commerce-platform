"""Deterministic helpers and fakes for phase-three workflow tests."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.agents.catalog_agent import CatalogAgent
from agentic_commerce_platform.agents.inventory_agent import InventoryAgent
from agentic_commerce_platform.agents.marketing_agent import MarketingAgent
from agentic_commerce_platform.agents.profile_agent import UserProfileAgent
from agentic_commerce_platform.agents.recommendation_agent import RecommendationAgent
from agentic_commerce_platform.domain.agent_models import (
    CatalogFilters,
    CatalogOutput,
)
from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.domain.models import (
    AgentResult,
    RecommendationContext,
    RecommendationRequest,
)
from agentic_commerce_platform.infrastructure.data import (
    InMemoryCatalogRepository,
    InMemoryInventoryRepository,
    InMemoryUserBehaviorRepository,
)
from agentic_commerce_platform.infrastructure.llm import MockLLMProvider
from agentic_commerce_platform.orchestration.nodes import WorkflowNodes
from agentic_commerce_platform.orchestration.state import (
    RecommendationWorkflowState,
    build_initial_workflow_state,
)
from agentic_commerce_platform.orchestration.supervisor import (
    SupervisorOrchestrator,
    WorkflowRepositories,
)
from agentic_commerce_platform.settings import Settings


def make_request(
    *,
    user_id: str = "u-demo-001",
    query: str = "python",
    category: str | None = None,
    num_items: int = 3,
) -> RecommendationRequest:
    """Build a valid workflow request with explicit context."""
    return RecommendationRequest(
        user_id=user_id,
        num_items=num_items,
        context=RecommendationContext(
            keywords=[query] if query else [],
            category=category,
        ),
    )


def make_initial_state(
    *,
    request_id: str = "workflow-test-request",
    user_id: str = "u-demo-001",
    query: str = "python",
    category: str | None = None,
    num_items: int = 3,
) -> RecommendationWorkflowState:
    """Build the minimal state accepted by the compiled graph."""
    request = make_request(
        user_id=user_id,
        query=query,
        category=category,
        num_items=num_items,
    )
    return build_initial_workflow_state(request, request_id)


def make_catalog_output(products: list[Any]) -> CatalogOutput:
    """Build a deterministic catalog output for fake agents."""
    return CatalogOutput(
        products=products,
        matched_count=len(products),
        query="",
        filters=CatalogFilters(),
        source=DataSource.IN_MEMORY_DEMO,
    )


class FixedResultAgent(BaseAgent):
    """Test agent that returns a pre-built AgentResult without network or data."""

    def __init__(self, name: str, result: AgentResult) -> None:
        self._fixed_result = result
        super().__init__(name=name, timeout_seconds=1.0)

    async def execute(self, **kwargs: Any) -> AgentResult:
        return self._fixed_result


class ConcurrencyTracker:
    """Record observed overlap between the profile and catalog branches."""

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.starts: list[float] = []
        self.ends: list[float] = []

    def enter(self) -> None:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.starts.append(time.perf_counter())

    def leave(self) -> None:
        self.active -= 1
        self.ends.append(time.perf_counter())


class SlowFixedAgent(FixedResultAgent):
    """Test agent with a configurable delay and concurrency observation."""

    def __init__(
        self,
        name: str,
        result: AgentResult,
        *,
        delay_seconds: float,
        tracker: ConcurrencyTracker | None = None,
    ) -> None:
        self._delay_seconds = delay_seconds
        self._tracker = tracker
        super().__init__(name, result)

    async def execute(self, **kwargs: Any) -> AgentResult:
        if self._tracker is not None:
            self._tracker.enter()
        try:
            await asyncio.sleep(self._delay_seconds)
            return self._fixed_result
        finally:
            if self._tracker is not None:
                self._tracker.leave()


@dataclass
class WorkflowComponents:
    """Real phase-two dependencies used by phase-three tests."""

    supervisor: SupervisorOrchestrator
    agents: dict[str, BaseAgent] = field(default_factory=dict)
    repositories: WorkflowRepositories | None = None


def make_workflow_nodes(settings: Settings) -> WorkflowNodes:
    """Build nodes with real phase-two agents and in-memory repositories."""
    provider = MockLLMProvider()
    behavior_repo = InMemoryUserBehaviorRepository()
    catalog_repo = InMemoryCatalogRepository()
    inventory_repo = InMemoryInventoryRepository()
    nodes = WorkflowNodes(
        profile_agent=UserProfileAgent(behavior_repo, provider),
        catalog_agent=CatalogAgent(catalog_repo, provider),
        recommendation_agent=RecommendationAgent(provider),
        inventory_agent=InventoryAgent(inventory_repo, provider),
        marketing_agent=MarketingAgent(provider),
    )
    return nodes


def make_supervisor(
    settings: Settings,
    *,
    agent_overrides: dict[str, BaseAgent] | None = None,
    provider: MockLLMProvider | None = None,
) -> SupervisorOrchestrator:
    """Build a Supervisor with explicit in-memory dependencies and optional fakes."""
    llm_provider = provider or MockLLMProvider()
    behavior_repo = InMemoryUserBehaviorRepository()
    catalog_repo = InMemoryCatalogRepository()
    inventory_repo = InMemoryInventoryRepository()
    repositories = WorkflowRepositories(
        user_behavior=behavior_repo,
        catalog=catalog_repo,
        inventory=inventory_repo,
    )
    agents: dict[str, BaseAgent] = {
        "user_profile_agent": UserProfileAgent(behavior_repo, llm_provider),
        "catalog_agent": CatalogAgent(catalog_repo, llm_provider),
        "recommendation_agent": RecommendationAgent(llm_provider),
        "inventory_agent": InventoryAgent(inventory_repo, llm_provider),
        "marketing_agent": MarketingAgent(llm_provider),
    }
    if agent_overrides:
        agents.update(agent_overrides)
    return SupervisorOrchestrator(
        profile_agent=agents["user_profile_agent"],  # type: ignore[arg-type]
        catalog_agent=agents["catalog_agent"],  # type: ignore[arg-type]
        recommendation_agent=agents["recommendation_agent"],  # type: ignore[arg-type]
        inventory_agent=agents["inventory_agent"],  # type: ignore[arg-type]
        marketing_agent=agents["marketing_agent"],  # type: ignore[arg-type]
        repositories=repositories,
        llm_provider=llm_provider,
        settings=settings,
    )


def agent_result(
    name: str,
    *,
    success: bool,
    data: dict[str, Any] | None = None,
    error: str | None = None,
    confidence: float | None = None,
) -> AgentResult:
    """Build a valid AgentResult for fake agents."""
    return AgentResult(
        agent_name=name,
        success=success,
        error=error,
        confidence=confidence,
        data=data or {},
    )
