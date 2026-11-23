"""In-memory user behavior adapter backed by phase-two demonstration data."""

from __future__ import annotations

from collections.abc import Sequence

from agentic_commerce_platform.domain.agent_models import UserBehaviorRecord
from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.infrastructure.data.demo_data import DEMO_BEHAVIORS

__all__ = ["InMemoryUserBehaviorRepository"]


class InMemoryUserBehaviorRepository:
    """Deterministic, read-only user behavior repository.

    The default records are phase-two in-memory demo data. Reads return deep
    copies so callers cannot mutate the repository's internal records.
    """

    def __init__(self, records: Sequence[UserBehaviorRecord] | None = None) -> None:
        """Initialize the repository.

        Args:
            records: Optional behavior records. Defaults to ``DEMO_BEHAVIORS``.

        Raises:
            ValueError: If duplicate user IDs are supplied.
        """
        source_records = list(records) if records is not None else list(DEMO_BEHAVIORS)
        indexed: dict[str, UserBehaviorRecord] = {}
        for record in source_records:
            if record.user_id in indexed:
                raise ValueError(f"duplicate user behavior record: {record.user_id!r}")
            indexed[record.user_id] = record.model_copy(deep=True)
        self._records = indexed

    @property
    def source(self) -> DataSource:
        """Return the explicit in-memory demo provenance marker."""
        return DataSource.IN_MEMORY_DEMO

    def get_behavior(self, user_id: str) -> UserBehaviorRecord | None:
        """Return a copy of a user's behavior, or ``None`` for unknown users."""
        record = self._records.get(user_id)
        return record.model_copy(deep=True) if record is not None else None
