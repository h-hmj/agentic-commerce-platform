"""Tests for the deterministic offline mock LLM provider."""

from __future__ import annotations

import pytest

from agentic_commerce_platform.domain.errors import ExternalServiceError
from agentic_commerce_platform.infrastructure.llm import (
    DEFAULT_MOCK_RESPONSE,
    LLMProvider,
    MockLLMProvider,
)


async def test_mock_provider_is_deterministic_and_clearly_mocked() -> None:
    """The default response is stable and explicitly identifies itself as mock."""
    provider = MockLLMProvider()

    first = await provider.generate("first prompt")
    second = await provider.generate(
        "different prompt",
        system_prompt="different system prompt",
        metadata={"trace": "ignored"},
    )

    assert first == second == DEFAULT_MOCK_RESPONSE
    assert "MOCK" in first
    assert "不是真实大模型" in first
    assert "真实商品推荐" in first


async def test_mock_provider_supports_custom_fixed_response() -> None:
    """A custom fixed response is returned unchanged."""
    provider = MockLLMProvider(response="fixed test response")

    assert await provider.generate("anything") == "fixed test response"
    assert provider.is_configured_to_fail is False


async def test_mock_provider_can_simulate_failure() -> None:
    """Failure mode raises a project-level external service error."""
    provider = MockLLMProvider(
        fail=True,
        failure_message="simulated provider outage",
    )

    assert provider.is_configured_to_fail is True
    with pytest.raises(ExternalServiceError) as exc_info:
        await provider.generate("prompt")

    assert exc_info.value.code == "external_service_error"
    assert exc_info.value.service_name == "mock_llm"
    assert "simulated provider outage" in str(exc_info.value)


def test_mock_provider_rejects_blank_configuration() -> None:
    """Blank fixed responses and failure messages are invalid."""
    with pytest.raises(ValueError):
        MockLLMProvider(response="   ")
    with pytest.raises(ValueError):
        MockLLMProvider(failure_message="  ")


def test_mock_provider_implements_protocol_without_credentials() -> None:
    """The mock satisfies the runtime-checkable provider contract."""
    provider = MockLLMProvider()

    assert isinstance(provider, LLMProvider)
