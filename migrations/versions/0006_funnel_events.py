"""Add funnel_events table.

Revision ID: 0006_funnel_events
Revises: 0005_amneziawg_clients
Create Date: 2026-07-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0006_funnel_events"
down_revision = "0005_amneziawg_clients"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "funnel_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=32), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "event", name="uq_funnel_events_user_event"),
    )
    op.create_index("ix_funnel_events_user_id", "funnel_events", ["user_id"])
    op.create_index("ix_funnel_events_event", "funnel_events", ["event"])


def downgrade() -> None:
    op.drop_index("ix_funnel_events_event", table_name="funnel_events")
    op.drop_index("ix_funnel_events_user_id", table_name="funnel_events")
    op.drop_table("funnel_events")
