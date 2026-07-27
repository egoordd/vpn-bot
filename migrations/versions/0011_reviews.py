"""Add reviews — user-submitted rating + text, with a rewarded flag.

Revision ID: 0011_reviews
Revises: 0010_user_source
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0011_reviews"
down_revision = "0010_user_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("rewarded", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_reviews_user_id", table_name="reviews")
    op.drop_table("reviews")
