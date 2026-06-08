"""Add nodes table.

Revision ID: 0002_nodes
Revises: 0001_initial
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0002_nodes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("tier", sa.String(length=32), server_default="premium", nullable=False),
        sa.Column("capacity", sa.Integer(), server_default="0", nullable=False),
        sa.Column("region", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("provider_instance_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("panel_node_id", sa.String(length=128), nullable=True),
        sa.Column("current_users", sa.Integer(), server_default="0", nullable=False),
        sa.Column("static_ips", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip_address"),
        sa.UniqueConstraint("panel_node_id"),
        sa.UniqueConstraint("provider_instance_id"),
    )
    op.create_index(op.f("ix_nodes_provider"), "nodes", ["provider"], unique=False)
    op.create_index(op.f("ix_nodes_region"), "nodes", ["region"], unique=False)
    op.create_index(op.f("ix_nodes_status"), "nodes", ["status"], unique=False)
    op.create_index(op.f("ix_nodes_tier"), "nodes", ["tier"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_nodes_tier"), table_name="nodes")
    op.drop_index(op.f("ix_nodes_status"), table_name="nodes")
    op.drop_index(op.f("ix_nodes_region"), table_name="nodes")
    op.drop_index(op.f("ix_nodes_provider"), table_name="nodes")
    op.drop_table("nodes")
