"""Service for invoking the user profile agent independently."""

from __future__ import annotations

from agentic_commerce_platform.agents.profile_agent import UserProfileAgent
from agentic_commerce_platform.domain.agent_models import UserProfileInput, UserProfileOutput
from agentic_commerce_platform.domain.ports import UserBehaviorRepository
from agentic_commerce_platform.infrastructure.llm.base import LLMProvider
from agentic_commerce_platform.services.agent_runner import run_agent_for_output

__all__ = ["ProfileService"]


class ProfileService:
    """Assemble profile input, call exactly one agent, and return typed output."""

    def __init__(
        self,
        behavior_repository: UserBehaviorRepository,
        llm_provider: LLMProvider,
    ) -> None:
        """Create the service and inject its agent dependencies."""
        self._agent = UserProfileAgent(behavior_repository, llm_provider)

    @property
    def agent(self) -> UserProfileAgent:
        """Return the service-owned agent for introspection in tests."""
        return self._agent

    async def build_profile(self, request: UserProfileInput) -> UserProfileOutput:
        """Build a structured profile for one user."""
        return await run_agent_for_output(self._agent, request, UserProfileOutput)
