"""add unified messaging and attachments

Revision ID: 20260727_06
Revises: 20260726_05
Create Date: 2026-07-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_06"
down_revision: str | None = "20260726_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("subject", sa.String(length=300), nullable=True),
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
            "channel", "external_id",
            name="uq_conversations_channel_external",
        ),
    )
    op.create_index("ix_conversations_channel", "conversations", ["channel"])
    op.create_index(
        "ix_conversations_customer_id", "conversations", ["customer_id"]
    )
    op.create_index("ix_conversations_status", "conversations", ["status"])
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("external_message_id", sa.String(length=300), nullable=True),
        sa.Column("sender_type", sa.String(length=20), nullable=False),
        sa.Column("sender_id", sa.String(length=200), nullable=True),
        sa.Column("sender_name", sa.String(length=200), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "channel", "external_message_id",
            name="uq_messages_channel_external",
        ),
    )
    op.create_index("ix_messages_channel", "messages", ["channel"])
    op.create_index(
        "ix_messages_conversation_id", "messages", ["conversation_id"]
    )
    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=100), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_name"),
    )
    op.create_index(
        "ix_attachments_conversation_id",
        "attachments", ["conversation_id"],
    )
    op.create_index(
        "ix_attachments_message_id", "attachments", ["message_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_attachments_message_id", table_name="attachments")
    op.drop_index(
        "ix_attachments_conversation_id", table_name="attachments"
    )
    op.drop_table("attachments")
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_index("ix_messages_channel", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_conversations_status", table_name="conversations")
    op.drop_index("ix_conversations_customer_id", table_name="conversations")
    op.drop_index("ix_conversations_channel", table_name="conversations")
    op.drop_table("conversations")
