"""Add users.source — first-touch acquisition source from /start deep link.

Revision ID: 0010_user_source
Revises: 0009_payment_receipt_url
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0010_user_source"
down_revision = "0009_payment_receipt_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("source", sa.String(length=32), nullable=True))
    op.create_index("ix_users_source", "users", ["source"])


def downgrade() -> None:
    op.drop_index("ix_users_source", table_name="users")
    op.drop_column("users", "source")
