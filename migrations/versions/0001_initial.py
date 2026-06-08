"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("balance", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lang", sa.String(length=10), server_default="ru", nullable=False),
        sa.Column("referrer_id", sa.Integer(), nullable=True),
        sa.Column("ref_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("is_blocked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["referrer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True)
    op.create_index(op.f("ix_users_ref_code"), "users", ["ref_code"], unique=True)

    op.create_table(
        "plans",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price_rub", sa.Integer(), server_default="0", nullable=False),
        sa.Column("crypto_amount", sa.String(length=32), nullable=False),
        sa.Column("traffic_limit_bytes", sa.BigInteger(), nullable=True),
        sa.Column("device_limit", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_index(op.f("ix_plans_tier"), "plans", ["tier"], unique=False)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan", sa.String(length=50), nullable=False),
        sa.Column("tier", sa.String(length=32), server_default="standard", nullable=False),
        sa.Column("panel_username", sa.String(length=128), nullable=True),
        sa.Column("sub_token", sa.String(length=128), nullable=True),
        sa.Column("subscription_url", sa.String(length=2048), nullable=True),
        sa.Column("traffic_limit_bytes", sa.BigInteger(), nullable=True),
        sa.Column("traffic_used_bytes", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("device_limit", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("node_ids", sa.JSON(), nullable=True),
        sa.Column("static_ip", sa.String(length=45), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_subscriptions_expires_at"), "subscriptions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_subscriptions_is_active"), "subscriptions", ["is_active"], unique=False)
    op.create_index(op.f("ix_subscriptions_panel_username"), "subscriptions", ["panel_username"], unique=False)
    op.create_index(op.f("ix_subscriptions_status"), "subscriptions", ["status"], unique=False)
    op.create_index(op.f("ix_subscriptions_sub_token"), "subscriptions", ["sub_token"], unique=False)
    op.create_index(op.f("ix_subscriptions_tier"), "subscriptions", ["tier"], unique=False)
    op.create_index(op.f("ix_subscriptions_user_id"), "subscriptions", ["user_id"], unique=False)

    op.create_table(
        "wireguard_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("public_key", sa.String(length=255), nullable=False),
        sa.Column("private_key", sa.String(length=255), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=False),
        sa.Column("config_file_path", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip_address", name="uq_wireguard_keys_ip_address"),
        sa.UniqueConstraint("public_key"),
        sa.UniqueConstraint("user_id", name="uq_wireguard_keys_user_id"),
    )
    op.create_index(op.f("ix_wireguard_keys_user_id"), "wireguard_keys", ["user_id"], unique=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("provider", sa.String(length=32), server_default="cryptobot", nullable=False),
        sa.Column("external_invoice_id", sa.String(length=128), nullable=True),
        sa.Column("telegram_payment_charge_id", sa.String(length=255), nullable=True),
        sa.Column("provider_payment_charge_id", sa.String(length=255), nullable=True),
        sa.Column("invoice_payload", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_payload"),
    )
    op.create_index(op.f("ix_payments_external_invoice_id"), "payments", ["external_invoice_id"], unique=True)
    op.create_index(op.f("ix_payments_status"), "payments", ["status"], unique=False)
    op.create_index(op.f("ix_payments_user_id"), "payments", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payments_user_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_status"), table_name="payments")
    op.drop_index(op.f("ix_payments_external_invoice_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index(op.f("ix_wireguard_keys_user_id"), table_name="wireguard_keys")
    op.drop_table("wireguard_keys")
    op.drop_index(op.f("ix_subscriptions_user_id"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_tier"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_sub_token"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_status"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_panel_username"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_is_active"), table_name="subscriptions")
    op.drop_index(op.f("ix_subscriptions_expires_at"), table_name="subscriptions")
    op.drop_table("subscriptions")
    op.drop_index(op.f("ix_plans_tier"), table_name="plans")
    op.drop_table("plans")
    op.drop_index(op.f("ix_users_ref_code"), table_name="users")
    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_table("users")
