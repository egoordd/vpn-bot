"""Add users.web_password_hash for site email/password accounts.

Revision ID: 0008_user_web_password
Revises: 0007_user_email
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0008_user_web_password"
down_revision = "0007_user_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("web_password_hash", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "web_password_hash")
