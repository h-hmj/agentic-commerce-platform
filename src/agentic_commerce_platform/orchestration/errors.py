"""Errors raised by phase-three workflow orchestration."""

from __future__ import annotations

from agentic_commerce_platform.domain.errors import EcommercePlatformError

__all__ = ["WorkflowExecutionError", "WorkflowStateError"]


class WorkflowExecutionError(EcommercePlatformError):
    """Raised when the workflow executor itself cannot complete safely."""

    default_code = "workflow_execution_error"
    default_message = "The recommendation workflow failed to execute."


class WorkflowStateError(WorkflowExecutionError):
    """Raised when workflow state is malformed and cannot be aggregated."""

    default_code = "workflow_state_error"
    default_message = "The recommendation workflow state is invalid."
