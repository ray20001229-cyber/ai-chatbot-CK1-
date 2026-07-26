"""add calendar events

Revision ID: 20260726_04
Revises: 20260726_03
Create Date: 2026-07-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_04"
down_revision: str | None = "20260726_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.String(length=100), nullable=True),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type", "source_id", name="uq_calendar_events_source"
        ),
    )
    op.create_index(
        "ix_calendar_events_conversation_id",
        "calendar_events", ["conversation_id"],
    )
    op.create_index(
        "ix_calendar_events_customer_id",
        "calendar_events", ["customer_id"],
    )
    op.create_index(
        "ix_calendar_events_starts_at",
        "calendar_events", ["starts_at"],
    )
    op.create_index(
        "ix_calendar_events_status",
        "calendar_events", ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_events_status", table_name="calendar_events")
    op.drop_index("ix_calendar_events_starts_at", table_name="calendar_events")
    op.drop_index("ix_calendar_events_customer_id", table_name="calendar_events")
    op.drop_index(
        "ix_calendar_events_conversation_id", table_name="calendar_events"
    )
    op.drop_table("calendar_events")
