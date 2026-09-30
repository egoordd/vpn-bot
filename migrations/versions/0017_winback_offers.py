"""Add winback_offers — кому отправлено личное предложение «безлимит со скидкой».

Revision ID: 0017_winback_offers
Revises: 0016_web_session_epochs
Create Date: 2026-10-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0017_winback_offers"
down_revision = "0016_web_session_epochs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "winback_offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_winback_offers_user_id", "winback_offers", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_winback_offers_user_id", table_name="winback_offers")
    op.drop_table("winback_offers")
