"""Add link_clicks — anonymous per-campaign tap counter for /go/<campaign>.

Revision ID: 0012_link_clicks
Revises: 0011_reviews
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0012_link_clicks"
down_revision = "0011_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "link_clicks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign", sa.String(length=32), nullable=False),
        sa.Column("target", sa.String(length=16), server_default="bot", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_link_clicks_campaign", "link_clicks", ["campaign"])
    op.create_index("ix_link_clicks_created_at", "link_clicks", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_link_clicks_created_at", table_name="link_clicks")
    op.drop_index("ix_link_clicks_campaign", table_name="link_clicks")
    op.drop_table("link_clicks")
