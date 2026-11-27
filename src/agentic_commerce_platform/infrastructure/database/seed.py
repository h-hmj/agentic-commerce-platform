"""Idempotent seeding for clearly marked phase-two demonstration data."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from agentic_commerce_platform.domain.enums import BehaviorType
from agentic_commerce_platform.infrastructure.data.demo_data import (
    DEMO_BEHAVIORS,
    DEMO_INVENTORY,
    DEMO_PRODUCTS,
)
from agentic_commerce_platform.infrastructure.database.models import (
    InventoryRecordORM,
    ProductORM,
    UserBehaviorORM,
    UserORM,
)
from agentic_commerce_platform.infrastructure.database.session import DatabaseManager

__all__ = ["seed_demo_database"]


def seed_demo_database(database: DatabaseManager) -> dict[str, int]:
    """Seed demo products, inventory, users, and behavior events once.

    Existing rows are never overwritten, and behavior seeding is skipped for a
    demo user that already has historical events. All seeded records are demo
    data, not production data.
    """
    database.create_schema()
    now = datetime.now(UTC)
    product_by_id = {product.product_id: product for product in DEMO_PRODUCTS}
    counts = {"products": 0, "inventory": 0, "users": 0, "behaviors": 0}

    with database.session() as session:
        for product in DEMO_PRODUCTS:
            existing = session.scalar(
                select(ProductORM.id).where(ProductORM.product_id == product.product_id)
            )
            if existing is None:
                session.add(
                    ProductORM(
                        product_id=product.product_id,
                        name=product.name,
                        category=product.category,
                        description=product.description,
                        brand=product.brand,
                        price=product.price,
                        stock=product.stock,
                        tags=list(product.tags),
                        is_active=product.is_active,
                    )
                )
                counts["products"] += 1

        for product_id, stock in DEMO_INVENTORY:
            existing = session.scalar(
                select(InventoryRecordORM.id).where(
                    InventoryRecordORM.product_id == product_id
                )
            )
            if existing is None:
                session.add(
                    InventoryRecordORM(
                        product_id=product_id,
                        stock=stock,
                        reserved_stock=0,
                    )
                )
                counts["inventory"] += 1

        for behavior in DEMO_BEHAVIORS:
            user = session.scalar(
                select(UserORM).where(UserORM.user_id == behavior.user_id)
            )
            if user is None:
                created_at = (
                    now - timedelta(days=behavior.account_age_days)
                    if behavior.account_age_days is not None
                    else now
                )
                session.add(UserORM(user_id=behavior.user_id, created_at=created_at))
                counts["users"] += 1
                session.flush()

            existing_events = session.scalar(
                select(func.count(UserBehaviorORM.id)).where(
                    UserBehaviorORM.user_id == behavior.user_id
                )
            )
            if existing_events:
                continue

            event_specs: list[tuple[BehaviorType, str]] = []
            event_specs.extend((BehaviorType.VIEW, item) for item in behavior.recent_views)
            event_specs.extend((BehaviorType.CLICK, item) for item in behavior.recent_clicks)
            event_specs.extend(
                (BehaviorType.PURCHASE, item) for item in behavior.recent_purchases
            )
            base_days = behavior.days_since_last_active or 0
            for index, (behavior_type, item_id) in enumerate(event_specs):
                product = product_by_id.get(item_id)
                session.add(
                    UserBehaviorORM(
                        user_id=behavior.user_id,
                        behavior_type=behavior_type.value,
                        item_id=item_id,
                        category=product.category if product else None,
                        amount=(
                            behavior.average_order_value
                            if behavior_type is BehaviorType.PURCHASE
                            else None
                        ),
                        metadata_json={
                            "seed": "phase-2 in-memory demo data",
                            "demo": True,
                        },
                        occurred_at=now
                        - timedelta(days=base_days, minutes=index),
                    )
                )
                counts["behaviors"] += 1

    return counts
