"""Tests for the correlation-aware logging configuration."""

from __future__ import annotations

import json
import logging
from io import StringIO

from agentic_commerce_platform.infrastructure.observability.logging import (
    agent_log_context,
    configure_logging,
    request_log_context,
)


def test_json_logging_contains_correlation_fields_and_safe_extras() -> None:
    """JSON logs expose the required context without application secrets."""
    stream = StringIO()
    logger = configure_logging("INFO", "json", stream=stream)
    test_logger = logging.getLogger("agentic_commerce_platform.test")

    try:
        with request_log_context("request-json-1"), agent_log_context("demo_agent"):
            test_logger.info(
                "test_event",
                extra={"http_path": "/health", "duration_ms": 1.25},
            )
    finally:
        configure_logging("WARNING", "console", stream=StringIO())

    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["level"] == "INFO"
    assert payload["logger"] == "agentic_commerce_platform.test"
    assert payload["message"] == "test_event"
    assert payload["request_id"] == "request-json-1"
    assert payload["agent_name"] == "demo_agent"
    assert payload["http_path"] == "/health"
    assert payload["duration_ms"] == 1.25
    assert "timestamp" in payload
    assert "api_key" not in payload
    assert logger.name == "agentic_commerce_platform"
