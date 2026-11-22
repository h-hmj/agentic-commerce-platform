"""Provider-agnostic LLM interface."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["LLMProvider"]


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal asynchronous contract implemented by every LLM adapter."""

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Generate a text completion.

        Args:
            prompt: User/task prompt. Implementations must not log it verbatim.
            system_prompt: Optional system-level instruction.
            metadata: Optional non-sensitive tracing metadata.

        Returns:
            Generated text.
        """
        ...
