"""Add wallet ledger and promo code tables.

Revision ID: 0003_wallet_promo
Revises: 0002_nodes
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0003_wallet_promo"
down_revision = "0002_nodes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wallet_transactions_user_id"), "wallet_transactions", ["user_id"], unique=False)
    op.create_index(op.f("ix_wallet_transactions_kind"), "wallet_transactions", ["kind"], unique=False)
    op.create_index(op.f("ix_wallet_transactions_reference"), "wallet_transactions", ["reference"], unique=False)

    op.create_table(
        "promo_codes",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        sa.Column("min_amount_kopecks", sa.Integer(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("per_user_limit", sa.Integer(), server_default="1", nullable=False),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_index(op.f("ix_promo_codes_is_active"), "promo_codes", ["is_active"], unique=False)

    op.create_table(
        "promo_redemptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("applied_amount", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["code"], ["promo_codes.code"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_promo_redemptions_code"), "promo_redemptions", ["code"], unique=False)
    op.create_index(op.f("ix_promo_redemptions_user_id"), "promo_redemptions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_promo_redemptions_user_id"), table_name="promo_redemptions")
    op.drop_index(op.f("ix_promo_redemptions_code"), table_name="promo_redemptions")
    op.drop_table("promo_redemptions")

    op.drop_index(op.f("ix_promo_codes_is_active"), table_name="promo_codes")
    op.drop_table("promo_codes")

    op.drop_index(op.f("ix_wallet_transactions_reference"), table_name="wallet_transactions")
    op.drop_index(op.f("ix_wallet_transactions_kind"), table_name="wallet_transactions")
    op.drop_index(op.f("ix_wallet_transactions_user_id"), table_name="wallet_transactions")
    op.drop_table("wallet_transactions")
