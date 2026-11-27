"""SQLAlchemy persistence adapters for phase four."""

from agentic_commerce_platform.infrastructure.database.base import Base
from agentic_commerce_platform.infrastructure.database.models import (
    InventoryRecordORM,
    ProductEmbeddingORM,
    ProductORM,
    UserBehaviorORM,
    UserORM,
    UserProfileORM,
)
from agentic_commerce_platform.infrastructure.database.session import DatabaseManager

__all__ = [
    "Base",
    "DatabaseManager",
    "InventoryRecordORM",
    "ProductEmbeddingORM",
    "ProductORM",
    "UserBehaviorORM",
    "UserORM",
    "UserProfileORM",
]
