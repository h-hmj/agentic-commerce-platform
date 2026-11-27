"""Phase-two in-memory data adapters and centralized demonstration data."""

from agentic_commerce_platform.infrastructure.data.demo_data import (
    DEMO_BEHAVIORS,
    DEMO_DATA_DISCLAIMER,
    DEMO_INVENTORY,
    DEMO_PRODUCTS,
)
from agentic_commerce_platform.infrastructure.data.in_memory_catalog import (
    InMemoryCatalogRepository,
)
from agentic_commerce_platform.infrastructure.data.in_memory_inventory import (
    InMemoryInventoryRepository,
)
from agentic_commerce_platform.infrastructure.data.in_memory_user_behavior import (
    InMemoryUserBehaviorRepository,
)
from agentic_commerce_platform.infrastructure.data.in_memory_user_profile import (
    InMemoryUserProfileRepository,
)

__all__ = [
    "DEMO_BEHAVIORS",
    "DEMO_DATA_DISCLAIMER",
    "DEMO_INVENTORY",
    "DEMO_PRODUCTS",
    "InMemoryCatalogRepository",
    "InMemoryInventoryRepository",
    "InMemoryUserBehaviorRepository",
    "InMemoryUserProfileRepository",
]
