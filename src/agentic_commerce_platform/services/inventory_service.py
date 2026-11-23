"""Service for invoking the inventory decision agent independently."""

from __future__ import annotations

from agentic_commerce_platform.agents.inventory_agent import InventoryAgent
from agentic_commerce_platform.domain.agent_models import InventoryInput, InventoryOutput
from agentic_commerce_platform.domain.ports import InventoryRepository
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider
from agentic_commerce_platform.services.agent_runner import run_agent_for_output

__all__ = ["InventoryService"]


class InventoryService:
    """Call the inventory agent through injected repository and LLM dependencies."""

    def __init__(
        self,
        inventory_repository: InventoryRepository,
        llm_provider: LLMProvider,
    ) -> None:
        """Create the service and inject its agent dependencies."""
        self._agent = InventoryAgent(inventory_repository, llm_provider)

    @property
    def agent(self) -> InventoryAgent:
        """Return the service-owned agent for introspection in tests."""
        return self._agent

    async def evaluate_inventory(self, request: InventoryInput) -> InventoryOutput:
        """Evaluate stock for one validated product set."""
        return await run_agent_for_output(self._agent, request, InventoryOutput)
