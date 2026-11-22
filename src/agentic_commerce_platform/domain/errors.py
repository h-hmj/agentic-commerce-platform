"""Project-level exception hierarchy.

The exceptions carry a stable machine-readable code and optional structured
details for server-side logging. API response messages are decided separately
by the API layer so internal exception text is never returned to clients.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "AgentExecutionError",
    "ConfigurationError",
    "EcommercePlatformError",
    "ExternalServiceError",
]


class EcommercePlatformError(Exception):
    """Base class for all expected platform errors."""

    default_code: str = "platform_error"
    default_message: str = "A platform error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Create a platform error.

        Args:
            message: Internal error description. API layers must not expose it
                verbatim unless it has been reviewed as safe.
            code: Stable machine-readable error code.
            details: Optional structured context for logs. It is not returned
                to API clients by default.
        """
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.details: dict[str, Any] = dict(details or {})
        super().__init__(self.message)


class ConfigurationError(EcommercePlatformError):
    """Raised when application configuration is missing or invalid."""

    default_code = "configuration_error"
    default_message = "Application configuration is invalid."


class AgentExecutionError(EcommercePlatformError):
    """Raised when an agent cannot produce a usable result."""

    default_code = "agent_execution_error"
    default_message = "An agent failed to execute."

    def __init__(
        self,
        message: str | None = None,
        *,
        agent_name: str | None = None,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Create an agent execution error.

        Args:
            message: Internal description of the failure.
            agent_name: Name of the agent that failed, when available.
            code: Optional stable error code override.
            details: Optional structured context for logs.
        """
        merged_details = dict(details or {})
        if agent_name:
            merged_details.setdefault("agent_name", agent_name)
        self.agent_name = agent_name
        super().__init__(message, code=code, details=merged_details)


class ExternalServiceError(EcommercePlatformError):
    """Raised when a dependency such as an LLM provider is unavailable."""

    default_code = "external_service_error"
    default_message = "An external service failed."

    def __init__(
        self,
        message: str | None = None,
        *,
        service_name: str | None = None,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Create an external service error.

        Args:
            message: Internal description of the failure.
            service_name: Name of the failing dependency, when available.
            code: Optional stable error code override.
            details: Optional structured context for logs.
        """
        merged_details = dict(details or {})
        if service_name:
            merged_details.setdefault("service_name", service_name)
        self.service_name = service_name
        super().__init__(message, code=code, details=merged_details)
