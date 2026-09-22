"""Add web_session_epochs — «выйти на всех устройствах» для сессий сайта.

Revision ID: 0016_web_session_epochs
Revises: 0015_web_checkouts
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0016_web_session_epochs"
down_revision = "0015_web_checkouts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "web_session_epochs",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("web_session_epochs")
