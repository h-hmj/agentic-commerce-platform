"""Phase-2 in-memory demo data.

This module contains deterministic demonstration records only. It is **not**
real catalog, inventory, or customer behavior data. No production system,
database, or external service is represented here.
"""

from __future__ import annotations

from decimal import Decimal

from agentic_commerce_platform.domain.agent_models import UserBehaviorRecord
from agentic_commerce_platform.domain.models import Product

__all__ = [
    "DEMO_BEHAVIORS",
    "DEMO_DATA_DISCLAIMER",
    "DEMO_INVENTORY",
    "DEMO_PRODUCTS",
]

DEMO_DATA_DISCLAIMER = (
    "Phase-2 in-memory demo data. Not real catalog, inventory, or customer data."
)

# Centralized, deterministic phase-2 demonstration products.
DEMO_PRODUCTS: tuple[Product, ...] = (
    Product(
        product_id="p-001",
        name="Python 编程实战",
        category="books",
        price=Decimal("89.00"),
        stock=12,
        tags=["python", "programming", "backend"],
    ),
    Product(
        product_id="p-002",
        name="Clean Architecture 实践",
        category="books",
        price=Decimal("109.00"),
        stock=5,
        tags=["architecture", "software", "backend"],
    ),
    Product(
        product_id="p-003",
        name="机械键盘 K87",
        category="electronics",
        price=Decimal("299.00"),
        stock=0,
        tags=["keyboard", "office", "gaming"],
    ),
    Product(
        product_id="p-004",
        name="降噪耳机 Air",
        category="electronics",
        price=Decimal("699.00"),
        stock=8,
        tags=["headphones", "travel", "music"],
    ),
    Product(
        product_id="p-005",
        name="咖啡豆礼盒",
        category="grocery",
        price=Decimal("128.00"),
        stock=20,
        tags=["coffee", "gift"],
    ),
    Product(
        product_id="p-006",
        name="入门手冲咖啡壶",
        category="home",
        price=Decimal("159.00"),
        stock=2,
        tags=["coffee", "kitchen"],
    ),
    Product(
        product_id="p-007",
        name="人体工学椅",
        category="home",
        price=Decimal("899.00"),
        stock=4,
        tags=["office", "furniture", "premium"],
    ),
    Product(
        product_id="p-008",
        name="数据科学入门",
        category="books",
        price=Decimal("129.00"),
        stock=6,
        tags=["python", "data", "machine-learning"],
    ),
    Product(
        product_id="p-009",
        name="旅行收纳包",
        category="travel",
        price=Decimal("59.00"),
        stock=15,
        tags=["travel", "budget"],
    ),
    Product(
        product_id="p-010",
        name="智能手表 S2",
        category="electronics",
        price=Decimal("1299.00"),
        stock=3,
        tags=["wearable", "premium", "fitness"],
    ),
)

# Inventory is intentionally a separate source of truth from Product.stock so
# agents exercise repository injection rather than mutating catalog objects.
DEMO_INVENTORY: tuple[tuple[str, int], ...] = (
    ("p-001", 12),
    ("p-002", 5),
    ("p-003", 0),
    ("p-004", 8),
    ("p-005", 20),
    ("p-006", 2),
    ("p-007", 4),
    ("p-008", 6),
    ("p-009", 15),
    ("p-010", 3),
)

# Deterministic behavior records for demo users. These are illustrative only.
DEMO_BEHAVIORS: tuple[UserBehaviorRecord, ...] = (
    UserBehaviorRecord(
        user_id="u-demo-001",
        recent_views=["p-001", "p-002", "p-008"],
        recent_clicks=["p-001", "p-004"],
        recent_purchases=["p-001"],
        category_counts={"books": 4, "electronics": 2, "home": 1},
        average_order_value=Decimal("680.00"),
        days_since_last_active=2,
        account_age_days=420,
    ),
    UserBehaviorRecord(
        user_id="u-demo-002",
        recent_views=["p-009", "p-005", "p-006"],
        recent_clicks=["p-009"],
        recent_purchases=["p-009"],
        category_counts={"travel": 2, "grocery": 2, "home": 1},
        average_order_value=Decimal("59.00"),
        days_since_last_active=3,
        account_age_days=150,
    ),
    UserBehaviorRecord(
        user_id="u-demo-003",
        recent_views=["p-004", "p-003"],
        recent_clicks=["p-004"],
        recent_purchases=["p-004"],
        category_counts={"electronics": 3},
        average_order_value=Decimal("320.00"),
        days_since_last_active=45,
        account_age_days=720,
    ),
    UserBehaviorRecord(
        user_id="u-demo-004",
        recent_views=["p-001"],
        recent_clicks=[],
        recent_purchases=[],
        category_counts={"books": 1},
        average_order_value=None,
        days_since_last_active=1,
        account_age_days=2,
    ),
)
