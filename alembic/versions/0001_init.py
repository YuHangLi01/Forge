"""init forge and langgraph schemas

Revision ID: 0001
Revises:
Create Date: 2026-04-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS langgraph")
    op.execute("CREATE SCHEMA IF NOT EXISTS forge")

    op.create_table(
        "tasks",
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("chat_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("intent_json", postgresql.JSONB(), nullable=True),
        sa.Column("plan_json", postgresql.JSONB(), nullable=True),
        sa.Column("doc_id", sa.String(128), nullable=True),
        sa.Column("ppt_id", sa.String(128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="forge",
    )

    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(256), nullable=False, server_default=""),
        sa.Column("style_hint_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="forge",
    )

    op.create_table(
        "event_processed",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="forge",
    )

    op.create_index(
        "ix_forge_tasks_user_id",
        "tasks",
        ["user_id"],
        schema="forge",
    )


def downgrade() -> None:
    op.drop_index("ix_forge_tasks_user_id", table_name="tasks", schema="forge")
    op.drop_table("event_processed", schema="forge")
    op.drop_table("user_profiles", schema="forge")
    op.drop_table("tasks", schema="forge")
    op.execute("DROP SCHEMA IF EXISTS forge")
    op.execute("DROP SCHEMA IF EXISTS langgraph")
