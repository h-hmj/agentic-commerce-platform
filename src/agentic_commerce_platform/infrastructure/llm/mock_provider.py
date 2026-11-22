"""Deterministic, fully offline LLM provider for phase-one development and tests."""

from __future__ import annotations

from typing import Any

from agentic_commerce_platform.domain.errors import ExternalServiceError

__all__ = ["DEFAULT_MOCK_RESPONSE", "MockLLMProvider"]

DEFAULT_MOCK_RESPONSE = (
    "【MOCK LLM】这是离线模拟输出，不是真实大模型生成内容，"
    "也不包含真实商品推荐。"
)


class MockLLMProvider:
    """Offline LLM provider with configurable, deterministic success or failure.

    The provider never performs network I/O, never reads an API key, and returns
    the same text regardless of the prompt. It exists solely to exercise the
    application wiring and the agent abstraction.
    """

    def __init__(
        self,
        *,
        response: str | None = None,
        fail: bool = False,
        failure_message: str = "Mock LLM provider simulated a failure.",
    ) -> None:
        """Configure the mock provider.

        Args:
            response: Optional fixed response text. Must be non-blank when set.
            fail: When true, every call raises :class:`ExternalServiceError`.
            failure_message: Message attached to simulated failures.

        Raises:
            ValueError: If a custom response is blank.
        """
        if response is not None and not response.strip():
            raise ValueError("response must not be blank when provided")
        if not failure_message.strip():
            raise ValueError("failure_message must not be blank")
        self._response = response if response is not None else DEFAULT_MOCK_RESPONSE
        self._fail = fail
        self._failure_message = failure_message

    @property
    def is_configured_to_fail(self) -> bool:
        """Whether this provider will simulate a failure."""
        return self._fail

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Return a fixed mock string or raise a simulated external failure.

        Args:
            prompt: Ignored by design; this method performs no generation.
            system_prompt: Ignored by design.
            metadata: Ignored by design and never logged.

        Returns:
            The configured fixed response.

        Raises:
            ExternalServiceError: When the provider is configured to fail.
        """
        if self._fail:
            raise ExternalServiceError(
                self._failure_message,
                service_name="mock_llm",
                details={"provider": "mock"},
            )
        return self._response
