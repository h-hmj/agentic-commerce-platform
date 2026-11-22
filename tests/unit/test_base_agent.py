"""Tests for the BaseAgent lifecycle contract."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentic_commerce_platform.agents.base import BaseAgent
from agentic_commerce_platform.domain.models import AgentResult


class SuccessfulAgent(BaseAgent):
    """Test agent that returns a deliberately misnamed result for normalization."""

    def __init__(self) -> None:
        super().__init__(name="successful_agent", timeout_seconds=1.0)

    async def execute(self, **kwargs: Any) -> AgentResult:
        return AgentResult(
            agent_name="wrong_name",
            success=True,
            latency_ms=999.0,
            data={"received": kwargs.get("value", "missing")},
        )


class FailingAgent(BaseAgent):
    """Test agent that raises an ordinary exception."""

    def __init__(self) -> None:
        super().__init__(name="failing_agent", timeout_seconds=1.0)

    async def execute(self, **kwargs: Any) -> AgentResult:
        raise RuntimeError("simulated agent failure")


class SlowAgent(BaseAgent):
    """Test agent used to exercise timeout handling."""

    def __init__(self) -> None:
        super().__init__(name="slow_agent", timeout_seconds=0.01)

    async def execute(self, **kwargs: Any) -> AgentResult:
        await asyncio.sleep(0.2)
        return AgentResult(agent_name=self.name, success=True)


class ConfigurableAgent(BaseAgent):
    """Concrete agent used to validate constructor policy arguments."""

    async def execute(self, **kwargs: Any) -> AgentResult:
        return AgentResult(agent_name=self.name, success=True)


class FlakyAgent(BaseAgent):
    """Test agent that fails once and then succeeds under a retry policy."""

    def __init__(self) -> None:
        super().__init__(
            name="flaky_agent",
            timeout_seconds=1.0,
            max_retries=1,
            retry_backoff_seconds=0.0,
        )
        self.calls = 0

    def _should_retry(self, exc: BaseException, attempt: int) -> bool:
        return isinstance(exc, RuntimeError)

    async def execute(self, **kwargs: Any) -> AgentResult:
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient failure")
        return AgentResult(agent_name=self.name, success=True, data={"calls": self.calls})


async def test_base_agent_success_normalizes_name_and_latency() -> None:
    """Successful execution returns a structured result with base metrics."""
    result = await SuccessfulAgent().run(value="hello")

    assert result.success is True
    assert result.agent_name == "successful_agent"
    assert result.latency_ms >= 0.0
    assert result.data == {"received": "hello"}
    assert result.error is None


async def test_base_agent_converts_exception_to_failed_result() -> None:
    """Ordinary exceptions become structured failures instead of leaking."""
    result = await FailingAgent().run()

    assert result.success is False
    assert result.agent_name == "failing_agent"
    assert result.error is not None
    assert "RuntimeError" in result.error
    assert "simulated agent failure" in result.error
    assert result.confidence is None
    assert result.data == {}


async def test_base_agent_enforces_timeout() -> None:
    """A slow agent yields a structured timeout failure."""
    result = await SlowAgent().run()

    assert result.success is False
    assert "TimeoutError" in (result.error or "")
    assert "slow_agent" in (result.error or "")


async def test_base_agent_retry_extension_point() -> None:
    """Subclasses can opt into retries through the protected hook."""
    agent = FlakyAgent()

    result = await agent.run()

    assert agent.calls == 2
    assert result.success is True
    assert result.data == {"calls": 2}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "agent", "timeout_seconds": 0},
        {"name": "agent", "timeout_seconds": -1},
        {"name": "agent", "max_retries": -1},
        {"name": "agent", "retry_backoff_seconds": -0.1},
    ],
)
def test_base_agent_rejects_invalid_configuration(kwargs: dict[str, object]) -> None:
    """Agent execution policy is validated at construction time."""
    with pytest.raises(ValueError):
        ConfigurableAgent(**kwargs)


def test_base_agent_is_abstract() -> None:
    """The base class cannot be instantiated without execute()."""
    with pytest.raises(TypeError):
        BaseAgent(name="abstract")
