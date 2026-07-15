"""Add payments.receipt_url — «Мой налог» чек link once income is registered.

Revision ID: 0009_payment_receipt_url
Revises: 0008_user_web_password
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0009_payment_receipt_url"
down_revision = "0008_user_web_password"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("receipt_url", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "receipt_url")
