"""Add users.email for 54-ФЗ receipts.

Revision ID: 0007_user_email
Revises: 0006_funnel_events
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0007_user_email"
down_revision = "0006_funnel_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email")
