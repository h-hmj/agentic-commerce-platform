"""Create phase-four persistence tables.

Revision ID: 0001_phase4_initial
Revises:
Create Date: 2026-11-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_phase4_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index("ix_products_product_id", "products", ["product_id"])
    op.create_index("ix_products_name", "products", ["name"])
    op.create_index("ix_products_category", "products", ["category"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_users_user_id", "users", ["user_id"])

    op.create_table(
        "inventory_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("stock", sa.Integer(), nullable=False),
        sa.Column("reserved_stock", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index(
        "ix_inventory_records_product_id", "inventory_records", ["product_id"]
    )

    op.create_table(
        "user_behaviors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("behavior_type", sa.String(length=32), nullable=False),
        sa.Column("item_id", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
    )
    op.create_index("ix_user_behaviors_user_id", "user_behaviors", ["user_id"])
    op.create_index("ix_user_behaviors_occurred_at", "user_behaviors", ["occurred_at"])

    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("segments", sa.JSON(), nullable=False),
        sa.Column("preferred_categories", sa.JSON(), nullable=False),
        sa.Column("price_min", sa.Numeric(12, 2), nullable=False),
        sa.Column("price_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("recent_interests", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("memory_source", sa.String(length=32), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"]),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"])

    op.create_table(
        "product_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("collection", sa.String(length=80), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.product_id"]),
        sa.UniqueConstraint("product_id"),
    )
    op.create_index(
        "ix_product_embeddings_product_id", "product_embeddings", ["product_id"]
    )


def downgrade() -> None:
    op.drop_table("product_embeddings")
    op.drop_table("user_profiles")
    op.drop_table("user_behaviors")
    op.drop_table("inventory_records")
    op.drop_table("users")
    op.drop_table("products")
