"""Basic observability tests for workflow node and final-state logs."""

from __future__ import annotations

import json
from io import StringIO

from agentic_commerce_platform.infrastructure.observability.logging import (
    configure_logging,
)
from tests.workflow_helpers import make_request, make_supervisor


async def test_workflow_logs_include_correlation_and_node_fields(test_settings) -> None:
    """JSON workflow logs expose request, node, status, and duration fields."""
    stream = StringIO()
    configure_logging("INFO", "json", stream=stream)
    try:
        supervisor = make_supervisor(test_settings)
        await supervisor.run(
            make_request(query="python", num_items=2),
            request_id="observability-1",
        )
    finally:
        configure_logging("WARNING", "console", stream=StringIO())

    payloads = [
        json.loads(line)
        for line in stream.getvalue().splitlines()
        if line.strip()
    ]
    node_events = [
        payload
        for payload in payloads
        if payload["message"].startswith("workflow_node_")
    ]
    completed = next(
        payload
        for payload in payloads
        if payload["message"] == "workflow_completed"
    )
    aggregated = next(
        payload
        for payload in payloads
        if payload["message"] == "workflow_aggregated"
    )

    assert node_events
    assert all(payload["request_id"] == "observability-1" for payload in node_events)
    assert all(payload["current_node"] for payload in node_events)
    assert all(payload["duration_ms"] >= 0 for payload in node_events if "duration_ms" in payload)
    assert completed["workflow_status"] == "success"
    assert completed["final_product_count"] > 0
    assert aggregated["workflow_status"] == "success"
    assert aggregated["current_node"] == "aggregate"
    assert "api_key" not in stream.getvalue().lower()
    assert "llm_api_key" not in stream.getvalue().lower()
