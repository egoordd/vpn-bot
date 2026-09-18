"""Add mirror_utm_links and mirror_utm_visits — рекламные ссылки /utm зеркала.

Revision ID: 0014_mirror_utm_links
Revises: 0013_utm_links
Create Date: 2026-09-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0014_mirror_utm_links"
down_revision = "0013_utm_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mirror_utm_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mirror_utm_links_code", "mirror_utm_links", ["code"], unique=True)

    op.create_table(
        "mirror_utm_visits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_new_user", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mirror_utm_visits_code", "mirror_utm_visits", ["code"])
    op.create_index("ix_mirror_utm_visits_user_id", "mirror_utm_visits", ["user_id"])
    op.create_index("ix_mirror_utm_visits_created_at", "mirror_utm_visits", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_mirror_utm_visits_created_at", table_name="mirror_utm_visits")
    op.drop_index("ix_mirror_utm_visits_user_id", table_name="mirror_utm_visits")
    op.drop_index("ix_mirror_utm_visits_code", table_name="mirror_utm_visits")
    op.drop_table("mirror_utm_visits")
    op.drop_index("ix_mirror_utm_links_code", table_name="mirror_utm_links")
    op.drop_table("mirror_utm_links")
