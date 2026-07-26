"""add conversation memories

Revision ID: 20260726_02
Revises: 20260724_01
Create Date: 2026-07-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_02"
down_revision: str | None = "20260724_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "conversation_id",
            sa.String(length=100),
            server_default="default",
            nullable=False,
        ),
    )
    op.create_index("ix_tasks_conversation_id", "tasks", ["conversation_id"])
    op.create_table(
        "conversation_memories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.String(length=100), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("resume_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_memories_conversation_id",
        "conversation_memories",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_memories_task_id",
        "conversation_memories",
        ["task_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_conversation_memories_task_id",
        table_name="conversation_memories",
    )
    op.drop_index(
        "ix_conversation_memories_conversation_id",
        table_name="conversation_memories",
    )
    op.drop_table("conversation_memories")
    op.drop_index("ix_tasks_conversation_id", table_name="tasks")
    op.drop_column("tasks", "conversation_id")
