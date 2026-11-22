"""Standard-library logging with request/agent correlation context.

The formatter intentionally lives behind a small configuration function. A
future phase can replace the renderer with a JSON log shipper without changing
application log statements.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, TextIO

__all__ = ["agent_log_context", "configure_logging", "request_log_context"]

_PACKAGE_LOGGER_NAME = "agentic_commerce_platform"
_HANDLER_MARKER = "_agentic_commerce_platform_handler"
_REQUEST_ID_FIELD = "request_id"
_AGENT_NAME_FIELD = "agent_name"
_EXTRA_FIELDS = (
    "http_method",
    "http_path",
    "status_code",
    "duration_ms",
    "attempt",
    "error_code",
    "scene",
    "num_items",
)
_SUPPORTED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_SUPPORTED_FORMATS = {"console", "json"}

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_agent_name_var: ContextVar[str | None] = ContextVar("agent_name", default=None)


@contextmanager
def request_log_context(request_id: str) -> Iterator[None]:
    """Bind a request identifier to all logs emitted inside the context."""
    token = _request_id_var.set(request_id)
    try:
        yield
    finally:
        _request_id_var.reset(token)


@contextmanager
def agent_log_context(agent_name: str) -> Iterator[None]:
    """Bind an agent name to all logs emitted inside the context."""
    token = _agent_name_var.set(agent_name)
    try:
        yield
    finally:
        _agent_name_var.reset(token)


class _ContextDefaultsFilter(logging.Filter):
    """Ensure correlation fields always exist and use contextvar fallbacks."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, _REQUEST_ID_FIELD, None):
            record.request_id = _request_id_var.get() or "-"
        if not getattr(record, _AGENT_NAME_FIELD, None):
            record.agent_name = _agent_name_var.get() or "-"
        return True


class _PlatformFormatterMixin:
    """Shared timestamp rendering for console and JSON formatters."""

    def formatTime(
        self,
        record: logging.LogRecord,
        datefmt: str | None = None,  # noqa: ARG002 - logging API signature
    ) -> str:
        """Render an ISO-8601 timestamp with the local timezone offset."""
        moment = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone()
        return moment.isoformat(timespec="milliseconds")


class ConsoleFormatter(_PlatformFormatterMixin, logging.Formatter):
    """Human-readable single-line formatter with correlation fields."""

    def __init__(self) -> None:
        """Initialize the console formatter."""
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        """Format one record, including optional safe extra fields."""
        message = record.getMessage()
        fields = [
            f"request_id={getattr(record, _REQUEST_ID_FIELD, '-')}",
            f"agent_name={getattr(record, _AGENT_NAME_FIELD, '-')}",
        ]
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                fields.append(f"{field}={value}")
        line = (
            f"{self.formatTime(record)} | {record.levelname} | "
            f"{record.name} | {message} | {' '.join(fields)}"
        )
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


class JsonFormatter(_PlatformFormatterMixin, logging.Formatter):
    """JSON-lines formatter suitable for future structured log shipping."""

    def format(self, record: logging.LogRecord) -> str:
        """Format one record as a single JSON object."""
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, _REQUEST_ID_FIELD, "-"),
            "agent_name": getattr(record, _AGENT_NAME_FIELD, "-"),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(
    level: str = "INFO",
    log_format: str = "console",
    *,
    stream: TextIO | None = None,
) -> logging.Logger:
    """Configure the package logger once and return it.

    Args:
        level: Standard logging level name.
        log_format: Either ``console`` or ``json``.
        stream: Optional output stream, primarily for tests.

    Raises:
        ValueError: If the level or format is unsupported.
    """
    normalized_level = level.strip().upper()
    if normalized_level not in _SUPPORTED_LOG_LEVELS:
        raise ValueError(f"unsupported log level: {level!r}")

    normalized_format = log_format.strip().lower()
    if normalized_format not in _SUPPORTED_FORMATS:
        raise ValueError(f"unsupported log format: {log_format!r}")

    logger = logging.getLogger(_PACKAGE_LOGGER_NAME)
    logger.setLevel(getattr(logging, normalized_level))
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()

    output_stream: TextIO = stream or sys.stderr
    handler: logging.Handler = logging.StreamHandler(output_stream)
    setattr(handler, _HANDLER_MARKER, True)
    handler.addFilter(_ContextDefaultsFilter())

    formatter: logging.Formatter
    if normalized_format == "json":
        formatter = JsonFormatter()
    else:
        formatter = ConsoleFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
