"""initial schema: robots, tasks, events, transactional outbox

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

JSON_TYPE = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "robots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("namespace", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="offline"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_task_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_robots_status", "robots", ["status"])
    op.create_index("ix_robots_status_seen", "robots", ["status", "last_seen_at"])

    op.create_table(
        "robot_capabilities",
        sa.Column("robot_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["robot_id"], ["robots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("robot_id", "name"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=128), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("robot_id", sa.Uuid(), nullable=True),
        sa.Column("command_id", sa.Uuid(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="120"),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result", JSON_TYPE, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["robot_id"], ["robots.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_id"),
    )
    op.create_index("ix_tasks_status", "tasks", ["status"])
    op.create_index("ix_tasks_type", "tasks", ["type"])
    op.create_index("ix_tasks_dispatch_queue", "tasks", ["status", "priority", "available_at"])
    op.create_index("ix_tasks_robot_status", "tasks", ["robot_id", "status"])
    op.create_index("ix_tasks_lease", "tasks", ["status", "lease_expires_at"])

    op.create_table(
        "task_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("robot_id", sa.Uuid(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])

    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=False),
        sa.Column("routing_key", sa.String(length=128), nullable=False),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("headers", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("expiration_ms", sa.Integer(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outbox_pending", "outbox_messages", ["sent_at", "available_at"])


def downgrade() -> None:
    op.drop_index("ix_outbox_pending", table_name="outbox_messages")
    op.drop_table("outbox_messages")
    op.drop_index("ix_task_events_task_id", table_name="task_events")
    op.drop_table("task_events")
    op.drop_index("ix_tasks_lease", table_name="tasks")
    op.drop_index("ix_tasks_robot_status", table_name="tasks")
    op.drop_index("ix_tasks_dispatch_queue", table_name="tasks")
    op.drop_index("ix_tasks_type", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_table("tasks")
    op.drop_table("robot_capabilities")
    op.drop_index("ix_robots_status_seen", table_name="robots")
    op.drop_index("ix_robots_status", table_name="robots")
    op.drop_table("robots")
