"""Add web_checkouts and web_password_resets — аккаунт на сайте после оплаты, сброс пароля.

Revision ID: 0015_web_checkouts
Revises: 0014_mirror_utm_links
Create Date: 2026-09-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0015_web_checkouts"
down_revision = "0014_mirror_utm_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "web_checkouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token", sa.String(length=32), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("plan", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("payment_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_account", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("initial_password_hash", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_web_checkouts_token", "web_checkouts", ["token"], unique=True)
    op.create_index("ix_web_checkouts_payment_id", "web_checkouts", ["payment_id"], unique=True)
    op.create_index("ix_web_checkouts_email", "web_checkouts", ["email"])
    op.create_index("ix_web_checkouts_status", "web_checkouts", ["status"])

    op.create_table(
        "web_password_resets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_web_password_resets_token_hash", "web_password_resets", ["token_hash"], unique=True)
    op.create_index("ix_web_password_resets_user_id", "web_password_resets", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_web_password_resets_user_id", table_name="web_password_resets")
    op.drop_index("ix_web_password_resets_token_hash", table_name="web_password_resets")
    op.drop_table("web_password_resets")
    op.drop_index("ix_web_checkouts_status", table_name="web_checkouts")
    op.drop_index("ix_web_checkouts_email", table_name="web_checkouts")
    op.drop_index("ix_web_checkouts_payment_id", table_name="web_checkouts")
    op.drop_index("ix_web_checkouts_token", table_name="web_checkouts")
    op.drop_table("web_checkouts")
