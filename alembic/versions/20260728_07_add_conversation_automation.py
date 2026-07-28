"""add conversation memory and reply automation

Revision ID: 20260728_07
Revises: 20260727_06
Create Date: 2026-07-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_07"
down_revision: str | None = "20260727_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "automation_enabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "handoff_status",
            sa.String(length=20),
            server_default="bot",
            nullable=False,
        ),
    )
    op.add_column(
        "conversations", sa.Column("handoff_reason", sa.Text(), nullable=True)
    )
    op.add_column(
        "conversations", sa.Column("memory_summary", sa.Text(), nullable=True)
    )
    op.add_column(
        "conversations",
        sa.Column("summary_updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_conversations_handoff_status",
        "conversations",
        ["handoff_status"],
    )
    op.add_column(
        "messages",
        sa.Column("reply_to_message_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column(
            "processing_status",
            sa.String(length=20),
            server_default="received",
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_messages_reply_to_message",
        "messages",
        "messages",
        ["reply_to_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_messages_reply_to_message_id",
        "messages",
        ["reply_to_message_id"],
        unique=True,
    )
    op.create_index(
        "ix_messages_processing_status",
        "messages",
        ["processing_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_processing_status", table_name="messages")
    op.drop_index("ix_messages_reply_to_message_id", table_name="messages")
    op.drop_constraint(
        "fk_messages_reply_to_message", "messages", type_="foreignkey"
    )
    op.drop_column("messages", "processing_status")
    op.drop_column("messages", "reply_to_message_id")
    op.drop_index(
        "ix_conversations_handoff_status", table_name="conversations"
    )
    op.drop_column("conversations", "summary_updated_at")
    op.drop_column("conversations", "memory_summary")
    op.drop_column("conversations", "handoff_reason")
    op.drop_column("conversations", "handoff_status")
    op.drop_column("conversations", "automation_enabled")
