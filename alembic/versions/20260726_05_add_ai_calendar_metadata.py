"""add ai calendar metadata

Revision ID: 20260726_05
Revises: 20260726_04
Create Date: 2026-07-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_05"
down_revision: str | None = "20260726_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks", sa.Column("calendar_title", sa.String(length=300))
    )
    op.add_column(
        "tasks", sa.Column("calendar_time_basis", sa.String(length=20))
    )
    op.add_column("tasks", sa.Column("calendar_reason", sa.Text()))
    op.add_column(
        "conversation_memories",
        sa.Column("calendar_title", sa.String(length=300)),
    )
    op.add_column(
        "conversation_memories",
        sa.Column("calendar_time_basis", sa.String(length=20)),
    )
    op.add_column(
        "conversation_memories", sa.Column("calendar_reason", sa.Text())
    )
    op.add_column(
        "calendar_events",
        sa.Column("time_basis", sa.String(length=20)),
    )
    op.add_column("calendar_events", sa.Column("time_reason", sa.Text()))


def downgrade() -> None:
    op.drop_column("calendar_events", "time_reason")
    op.drop_column("calendar_events", "time_basis")
    op.drop_column("conversation_memories", "calendar_reason")
    op.drop_column("conversation_memories", "calendar_time_basis")
    op.drop_column("conversation_memories", "calendar_title")
    op.drop_column("tasks", "calendar_time_basis")
    op.drop_column("tasks", "calendar_reason")
    op.drop_column("tasks", "calendar_title")
