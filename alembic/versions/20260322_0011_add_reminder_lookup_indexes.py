"""为 reminder 续执行匹配补充复合索引。"""

from alembic import op

revision = "20260322_0011"
down_revision = "20260322_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_reminders_pending_conversation_lookup",
        "reminders",
        ["status", "conversation_id", "created_at"],
    )
    op.create_index(
        "ix_reminders_pending_dispatch_lookup",
        "reminders",
        ["status", "dispatch_channel", "dispatch_recipient_id", "created_at"],
    )
    op.create_index(
        "ix_reminders_pending_dispatch_chat_lookup",
        "reminders",
        [
            "status",
            "dispatch_channel",
            "dispatch_recipient_id",
            "dispatch_chat_id",
            "dispatch_thread_id",
            "created_at",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reminders_pending_dispatch_chat_lookup",
        table_name="reminders",
    )
    op.drop_index(
        "ix_reminders_pending_dispatch_lookup",
        table_name="reminders",
    )
    op.drop_index(
        "ix_reminders_pending_conversation_lookup",
        table_name="reminders",
    )
