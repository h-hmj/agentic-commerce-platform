"""SQLAlchemy schema, seed, and repository tests on isolated SQLite databases."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from agentic_commerce_platform.domain.data_models import BehaviorEvent
from agentic_commerce_platform.domain.enums import BehaviorType, DataSource, UserSegment
from agentic_commerce_platform.infrastructure.database.repositories import (
    DatabaseCatalogRepository,
    DatabaseInventoryRepository,
    DatabaseUserBehaviorRepository,
    DatabaseUserProfileRepository,
)
from agentic_commerce_platform.infrastructure.database.seed import seed_demo_database
from tests.helpers import make_profile
from tests.phase4_helpers import make_database


def test_database_schema_and_idempotent_seed(tmp_path) -> None:
    """Required tables exist and repeated demo seeding does not duplicate rows."""
    database = make_database(tmp_path)
    try:
        tables = set(inspect(database.engine).get_table_names())
        assert {
            "products",
            "inventory_records",
            "users",
            "user_behaviors",
            "user_profiles",
            "product_embeddings",
        } <= tables
        second = seed_demo_database(database)
        assert second == {"products": 0, "inventory": 0, "users": 0, "behaviors": 0}
    finally:
        database.dispose()


def test_catalog_and_inventory_repositories(tmp_path) -> None:
    """Database catalog/inventory repositories return domain models and stock."""
    database = make_database(tmp_path)
    try:
        catalog = DatabaseCatalogRepository(database)
        inventory = DatabaseInventoryRepository(database)

        books = catalog.search(category="books", limit=2)
        assert catalog.source is DataSource.DATABASE
        assert books
        assert all(product.category == "books" for product in books)
        assert len(catalog.get_by_ids(["p-001", "p-003"])) == 2
        assert inventory.source is DataSource.DATABASE
        assert inventory.get_stock("p-001") == 12
        assert inventory.get_stock_levels(["p-001", "missing"]) == {
            "p-001": 12,
            "missing": None,
        }
        assert inventory.update_stock("p-001", 7) == 7
        assert inventory.get_stock("p-001") == 7
        with pytest.raises(ValueError):
            inventory.update_stock("p-001", -1)
    finally:
        database.dispose()


def test_behavior_repository_reads_and_writes_events(tmp_path) -> None:
    """Behavior history supports recent/type filters, writes, and aggregation."""
    database = make_database(tmp_path)
    try:
        repository = DatabaseUserBehaviorRepository(database)
        event = BehaviorEvent(
            user_id="new-user",
            behavior_type=BehaviorType.VIEW,
            item_id="p-001",
            category="books",
        )
        stored = repository.record_behavior(event)
        assert stored.user_id == "new-user"
        recent = repository.get_recent_behaviors("new-user", limit=10)
        assert len(recent) == 1
        assert repository.get_recent_behaviors(
            "new-user", behavior_type="purchase"
        ) == []
        aggregate = repository.get_behavior("u-demo-001")
        assert aggregate is not None
        assert aggregate.recent_purchases
        assert aggregate.category_counts
        assert repository.source is DataSource.DATABASE
    finally:
        database.dispose()


def test_profile_repository_upsert_and_invalidate(tmp_path) -> None:
    """Profiles save idempotently, read back as domain models, and invalidate."""
    database = make_database(tmp_path)
    try:
        repository = DatabaseUserProfileRepository(database)
        profile = make_profile(segments=[UserSegment.ACTIVE])
        first = repository.save_profile(profile)
        second = repository.save_profile(profile.model_copy(update={"confidence": 0.9}))
        loaded = repository.get_profile("u-test")

        assert first.profile.user_id == "u-test"
        assert second.profile.confidence == 0.9
        assert loaded is not None
        assert loaded.profile.confidence == 0.9
        assert loaded.profile.profile_persisted is True
        assert repository.invalidate("u-test") is True
        assert repository.get_profile("u-test") is None
        assert repository.invalidate("u-test") is False
    finally:
        database.dispose()
