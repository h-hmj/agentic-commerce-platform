"""Shared service-level execution and output-validation helper."""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.domain.errors import AgentExecutionError

__all__ = ["run_agent_for_output"]

logger = logging.getLogger(__name__)

_OutputT = TypeVar("_OutputT", bound=BaseModel)


async def run_agent_for_output(
    agent: BaseAgent,
    request: BaseModel,
    output_type: type[_OutputT],
) -> _OutputT:
    """Run an agent, convert failures to project errors, and parse typed output.

    Args:
        agent: Agent instance to invoke through its shared lifecycle.
        request: Validated Pydantic input passed as the ``request`` keyword.
        output_type: Specialized output model used to validate ``result.data``.

    Returns:
        The validated specialized output model.

    Raises:
        AgentExecutionError: If the agent fails or returns malformed data.
    """
    result = await agent.run(request=request)
    if not result.success:
        logger.error(
            "phase2_agent_failed",
            extra={"agent_name": result.agent_name},
        )
        raise AgentExecutionError(
            f"Agent '{result.agent_name}' returned a failed result.",
            agent_name=result.agent_name,
            details={"agent_error": result.error},
        )
    try:
        return output_type.model_validate(result.data)
    except ValidationError as exc:
        logger.exception(
            "phase2_agent_output_invalid",
            extra={"agent_name": result.agent_name},
        )
        raise AgentExecutionError(
            f"Agent '{result.agent_name}' returned invalid {output_type.__name__} data.",
            agent_name=result.agent_name,
        ) from exc
