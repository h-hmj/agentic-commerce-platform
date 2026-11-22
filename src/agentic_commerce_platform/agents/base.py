"""Common lifecycle, timing, logging, timeout, and retry behavior for agents."""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from agentic_commerce_platform.domain.errors import EcommercePlatformError
from agentic_commerce_platform.domain.models import AgentResult
from agentic_commerce_platform.infrastructure.observability.logging import agent_log_context

__all__ = ["BaseAgent"]

logger = logging.getLogger(__name__)
_MAX_ERROR_LENGTH = 1000


class BaseAgent(ABC):
    """Abstract base class for all agents.

    Subclasses implement :meth:`execute` and return a structured
    :class:`AgentResult`. :meth:`run` owns cross-cutting concerns: timing,
    logging, timeout enforcement, exception-to-result conversion, and an
    overridable retry policy.
    """

    def __init__(
        self,
        *,
        name: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 0,
        retry_backoff_seconds: float = 0.0,
    ) -> None:
        """Initialize the agent.

        Args:
            name: Non-blank logical agent name.
            timeout_seconds: Per-attempt timeout in seconds.
            max_retries: Number of retries after the initial attempt.
            retry_backoff_seconds: Delay between retry attempts.

        Raises:
            ValueError: If any execution policy value is invalid.
        """
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("agent name must not be blank")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if max_retries < 0:
            raise ValueError("max_retries must be zero or greater")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be zero or greater")

        self.name = normalized_name
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = max_retries
        self.retry_backoff_seconds = float(retry_backoff_seconds)

    async def run(self, **kwargs: Any) -> AgentResult:
        """Execute the agent and always return a structured result for failures.

        Cancellation and interpreter-level exceptions are not swallowed. All
        ordinary agent exceptions are converted to a failed :class:`AgentResult`
        and logged with server-side context; the public API layer decides how to
        expose that failure safely.

        Args:
            **kwargs: Agent-specific input passed to :meth:`execute`.

        Returns:
            A successful or failed structured agent result with measured latency.
        """
        started_at = time.perf_counter()
        max_attempts = self.max_retries + 1

        with agent_log_context(self.name):
            logger.info("agent_started", extra={"attempt": 1})

            for attempt in range(1, max_attempts + 1):
                try:
                    raw_result = await asyncio.wait_for(
                        self.execute(**kwargs),
                        timeout=self.timeout_seconds,
                    )
                    if not isinstance(raw_result, AgentResult):
                        raise TypeError(
                            f"{type(self).__name__}.execute() must return AgentResult, "
                            f"got {type(raw_result).__name__}"
                        )
                except asyncio.TimeoutError as exc:
                    error = (
                        f"TimeoutError: Agent '{self.name}' exceeded "
                        f"timeout of {self.timeout_seconds:.3f}s."
                    )
                    if self._can_retry(exc, attempt, max_attempts):
                        await self._handle_retry(exc, attempt)
                        continue
                    return self._failure_result(error, started_at, exc, attempt)
                except Exception as exc:
                    error = self._format_error(exc)
                    if self._can_retry(exc, attempt, max_attempts):
                        await self._handle_retry(exc, attempt)
                        continue
                    return self._failure_result(error, started_at, exc, attempt)

                latency_ms = (time.perf_counter() - started_at) * 1000.0
                result = raw_result.model_copy(
                    update={
                        "agent_name": self.name,
                        "latency_ms": latency_ms,
                    }
                )
                if result.success:
                    logger.info(
                        "agent_completed",
                        extra={"attempt": attempt, "duration_ms": round(latency_ms, 2)},
                    )
                else:
                    logger.warning(
                        "agent_completed_with_failure",
                        extra={"attempt": attempt, "duration_ms": round(latency_ms, 2)},
                    )
                return result

        # The loop always returns or continues; this is defensive and should
        # only be reached if the retry policy is changed incorrectly.
        raise RuntimeError(f"Agent '{self.name}' exited without a result")

    def _can_retry(self, exc: BaseException, attempt: int, max_attempts: int) -> bool:
        """Return whether another attempt is allowed by policy."""
        return attempt < max_attempts and self._should_retry(exc, attempt)

    def _should_retry(self, exc: BaseException, attempt: int) -> bool:
        """Retry-policy extension point.

        The default never retries. Subclasses can override this hook to retry
        transient provider failures while retaining the base class's consistent
        logging and result handling.

        Args:
            exc: The exception raised by the attempt.
            attempt: One-based number of the attempt that just failed.

        Returns:
            ``True`` to make another attempt, otherwise ``False``.
        """
        return False

    async def _handle_retry(self, exc: BaseException, attempt: int) -> None:
        """Log a retry decision and wait for the configured backoff."""
        extra: dict[str, Any] = {"attempt": attempt}
        if isinstance(exc, EcommercePlatformError):
            extra["error_code"] = exc.code
        logger.warning(
            "agent_attempt_failed_retrying: %s",
            self._format_error(exc),
            extra=extra,
        )
        if self.retry_backoff_seconds > 0:
            await asyncio.sleep(self.retry_backoff_seconds)

    def _failure_result(
        self,
        error: str,
        started_at: float,
        exc: BaseException,
        attempt: int,
    ) -> AgentResult:
        """Log a terminal failure and build a structured failed result."""
        latency_ms = (time.perf_counter() - started_at) * 1000.0
        extra: dict[str, Any] = {
            "attempt": attempt,
            "duration_ms": round(latency_ms, 2),
        }
        if isinstance(exc, EcommercePlatformError):
            extra["error_code"] = exc.code
        logger.error(
            "agent_failed: %s",
            error,
            extra=extra,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return AgentResult(
            agent_name=self.name,
            success=False,
            latency_ms=latency_ms,
            error=error,
            confidence=None,
            data={},
        )

    @staticmethod
    def _format_error(exc: BaseException) -> str:
        """Format an exception into a bounded error string for AgentResult."""
        message = str(exc).strip()
        rendered = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
        if len(rendered) > _MAX_ERROR_LENGTH:
            return f"{rendered[: _MAX_ERROR_LENGTH - 3]}..."
        return rendered

    @abstractmethod
    async def execute(self, **kwargs: Any) -> AgentResult:
        """Perform the agent-specific work.

        Implementations should raise exceptions on failure rather than
        swallowing them; :meth:`run` converts them into a failed result and
        records the failure.

        Args:
            **kwargs: Agent-specific input.

        Returns:
            A structured agent result.
        """
        raise NotImplementedError
