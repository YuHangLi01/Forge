"""add cost_metrics table

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-04

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cost_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("node_name", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        schema="forge",
    )
    op.create_index(
        "ix_forge_cost_metrics_task_id",
        "cost_metrics",
        ["task_id"],
        schema="forge",
    )


def downgrade() -> None:
    op.drop_index("ix_forge_cost_metrics_task_id", table_name="cost_metrics", schema="forge")
    op.drop_table("cost_metrics", schema="forge")
