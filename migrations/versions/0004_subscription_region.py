"""Add region column to subscriptions.

Revision ID: 0004_subscription_region
Revises: 0003_wallet_promo
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0004_subscription_region"
down_revision = "0003_wallet_promo"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscriptions", sa.Column("region", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("subscriptions", "region")
