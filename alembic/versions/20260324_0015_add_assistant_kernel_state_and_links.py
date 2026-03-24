"""补充 assistant kernel 状态与 reminder/task/memory 扩展字段。"""

import sqlalchemy as sa

from alembic import op

revision = "20260324_0015"
down_revision = "20260322_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tasks", sa.Column("linked_reminder_id", sa.String(length=36), nullable=True))
    op.add_column("tasks", sa.Column("source_type", sa.String(length=64), nullable=True))
    op.add_column("tasks", sa.Column("source_id", sa.String(length=255), nullable=True))
    op.create_index("ix_tasks_linked_reminder_id", "tasks", ["linked_reminder_id"])
    op.create_index("ix_tasks_source_type_source_id", "tasks", ["source_type", "source_id"])

    op.add_column("reminders", sa.Column("linked_task_id", sa.String(length=36), nullable=True))
    op.add_column("reminders", sa.Column("failure_stage", sa.String(length=64), nullable=True))
    op.add_column(
        "reminders",
        sa.Column("failure_reason_code", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "reminders",
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_reminders_linked_task_id", "reminders", ["linked_task_id"])
    op.create_index("ix_reminders_retryable_status", "reminders", ["retryable", "status"])
    op.alter_column("reminders", "retryable", server_default=None)

    op.add_column(
        "memories",
        sa.Column("memory_type", sa.String(length=32), nullable=False, server_default="note"),
    )
    op.add_column("memories", sa.Column("scope_object_type", sa.String(length=32), nullable=True))
    op.add_column("memories", sa.Column("scope_object_id", sa.String(length=36), nullable=True))
    op.add_column("memories", sa.Column("importance", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("memories", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_memories_scope_object", "memories", ["scope_object_type", "scope_object_id"])
    op.create_index("ix_memories_memory_type", "memories", ["memory_type"])
    op.alter_column("memories", "memory_type", server_default=None)
    op.alter_column("memories", "importance", server_default=None)

    op.create_table(
        "assistant_turn_states",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("focused_object_type", sa.String(length=32), nullable=True),
        sa.Column("focused_object_id", sa.String(length=36), nullable=True),
        sa.Column("dialogue_mode", sa.String(length=32), nullable=False, server_default="normal"),
        sa.Column("last_action_type", sa.String(length=64), nullable=True),
        sa.Column("last_action_success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("visible_candidates_json", sa.JSON(), nullable=True),
        sa.Column("pending_confirmation_json", sa.JSON(), nullable=True),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("conversation_id", "session_id"),
    )
    op.create_index(
        "ix_assistant_turn_states_updated_at",
        "assistant_turn_states",
        ["updated_at"],
    )
    op.alter_column("assistant_turn_states", "dialogue_mode", server_default=None)
    op.alter_column("assistant_turn_states", "last_action_success", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_assistant_turn_states_updated_at", table_name="assistant_turn_states")
    op.drop_table("assistant_turn_states")

    op.drop_index("ix_memories_memory_type", table_name="memories")
    op.drop_index("ix_memories_scope_object", table_name="memories")
    op.drop_column("memories", "expires_at")
    op.drop_column("memories", "importance")
    op.drop_column("memories", "scope_object_id")
    op.drop_column("memories", "scope_object_type")
    op.drop_column("memories", "memory_type")

    op.drop_index("ix_reminders_retryable_status", table_name="reminders")
    op.drop_index("ix_reminders_linked_task_id", table_name="reminders")
    op.drop_column("reminders", "retryable")
    op.drop_column("reminders", "failure_reason_code")
    op.drop_column("reminders", "failure_stage")
    op.drop_column("reminders", "linked_task_id")

    op.drop_index("ix_tasks_source_type_source_id", table_name="tasks")
    op.drop_index("ix_tasks_linked_reminder_id", table_name="tasks")
    op.drop_column("tasks", "source_id")
    op.drop_column("tasks", "source_type")
    op.drop_column("tasks", "linked_reminder_id")
