"""LLM provider abstraction, offline mock, and provider composition."""

from ecommerce_platform.domain.errors import ConfigurationError
from ecommerce_platform.infrastructure.llm.base import LLMProvider
from ecommerce_platform.infrastructure.llm.mock_provider import (
    DEFAULT_MOCK_RESPONSE,
    MockLLMProvider,
)
from ecommerce_platform.settings import Settings

__all__ = [
    "DEFAULT_MOCK_RESPONSE",
    "LLMProvider",
    "MockLLMProvider",
    "build_llm_provider",
]


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Build the configured LLM provider.

    Phase one deliberately supports only the offline mock adapter. Adding a
    real adapter later should happen in this function or a dedicated factory,
    keeping call sites provider-agnostic.

    Args:
        settings: Validated application settings.

    Returns:
        A provider implementing :class:`LLMProvider`.

    Raises:
        ConfigurationError: If the configured provider has no implementation.
    """
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    raise ConfigurationError(
        f"No LLM provider implementation is registered for {settings.llm_provider!r}."
    )
