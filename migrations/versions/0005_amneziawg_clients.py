"""Add amneziawg_clients table.

Revision ID: 0005_amneziawg_clients
Revises: 0004_subscription_region
Create Date: 2026-06-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0005_amneziawg_clients"
down_revision = "0004_subscription_region"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "amneziawg_clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("public_key", sa.String(length=255), nullable=False),
        sa.Column("private_key", sa.String(length=255), nullable=False),
        sa.Column("ip_index", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_amneziawg_clients_user_id"),
        sa.UniqueConstraint("ip_index", name="uq_amneziawg_clients_ip_index"),
        sa.UniqueConstraint("public_key", name="uq_amneziawg_clients_public_key"),
    )
    op.create_index("ix_amneziawg_clients_user_id", "amneziawg_clients", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_amneziawg_clients_user_id", table_name="amneziawg_clients")
    op.drop_table("amneziawg_clients")
