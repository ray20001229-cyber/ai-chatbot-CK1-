"""add customers, reminders and task management fields

Revision ID: 20260726_03
Revises: 20260726_02
Create Date: 2026-07-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_03"
down_revision: str | None = "20260726_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index("ix_customers_external_id", "customers", ["external_id"])
    op.add_column("tasks", sa.Column("customer_id", sa.Uuid(), nullable=True))
    op.add_column(
        "tasks",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_tasks_customer_id", "tasks", "customers",
        ["customer_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_tasks_customer_id", "tasks", ["customer_id"])
    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "triggered_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_type", "source_id", name="uq_reminders_source"
        ),
    )
    op.create_index(
        "ix_reminders_conversation_id", "reminders", ["conversation_id"]
    )
    op.create_index("ix_reminders_status", "reminders", ["status"])


def downgrade() -> None:
    op.drop_index("ix_reminders_status", table_name="reminders")
    op.drop_index("ix_reminders_conversation_id", table_name="reminders")
    op.drop_table("reminders")
    op.drop_index("ix_tasks_customer_id", table_name="tasks")
    op.drop_constraint("fk_tasks_customer_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "updated_at")
    op.drop_column("tasks", "customer_id")
    op.drop_index("ix_customers_external_id", table_name="customers")
    op.drop_table("customers")
