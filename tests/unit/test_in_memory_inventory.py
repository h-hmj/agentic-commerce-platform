"""Tests for the in-memory inventory adapter."""

from __future__ import annotations

import pytest

from agentic_commerce_platform.domain.enums import DataSource
from agentic_commerce_platform.infrastructure.data import InMemoryInventoryRepository


def test_inventory_lookup_and_unknown_product() -> None:
    """Known IDs return stock; unknown IDs return None."""
    repository = InMemoryInventoryRepository({"p-1": 5, "p-2": 0})

    assert repository.get_stock("p-1") == 5
    assert repository.get_stock("p-2") == 0
    assert repository.get_stock("missing") is None
    assert repository.source is DataSource.IN_MEMORY_DEMO


def test_inventory_does_not_mutate_seed_mapping() -> None:
    """The repository owns an internal copy of the supplied mapping."""
    seed = {"p-1": 5}

    repository = InMemoryInventoryRepository(seed)
    seed["p-1"] = 0

    assert repository.get_stock("p-1") == 5


@pytest.mark.parametrize("invalid_stock", [-1, 1.5, True, "2"])
def test_inventory_rejects_invalid_seed_values(invalid_stock: object) -> None:
    """Invalid stock seeds are rejected at construction time."""
    with pytest.raises(ValueError, match="non-negative integer"):
        InMemoryInventoryRepository({"p-1": invalid_stock})  # type: ignore[dict-item]


def test_demo_inventory_is_available_without_custom_seed() -> None:
    """The default inventory is deterministic phase-two demo data."""
    repository = InMemoryInventoryRepository()

    assert repository.get_stock("p-001") == 12
    assert repository.source is DataSource.IN_MEMORY_DEMO
