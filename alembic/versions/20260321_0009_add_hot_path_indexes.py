"""为审计与会话热路径补充索引。"""

from alembic import op

revision = "20260321_0009"
down_revision = "20260321_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_conversation_bindings_lookup",
        "conversation_bindings",
        ["channel", "user_identity", "chat_id", "thread_id"],
    )
    op.create_index(
        "ix_message_event_logs_session_id",
        "message_event_logs",
        ["session_id"],
    )
    op.create_index(
        "ix_message_event_logs_channel",
        "message_event_logs",
        ["channel"],
    )
    op.create_index(
        "ix_workflow_event_logs_session_id",
        "workflow_event_logs",
        ["session_id"],
    )
    op.create_index(
        "ix_workflow_event_logs_workflow_type",
        "workflow_event_logs",
        ["workflow_type"],
    )
    op.create_index(
        "ix_model_invocation_logs_conversation_id",
        "model_invocation_logs",
        ["conversation_id"],
    )
    op.create_index(
        "ix_model_invocation_logs_provider",
        "model_invocation_logs",
        ["provider"],
    )
    op.create_index(
        "ix_tool_invocation_logs_conversation_id",
        "tool_invocation_logs",
        ["conversation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tool_invocation_logs_conversation_id",
        table_name="tool_invocation_logs",
    )
    op.drop_index(
        "ix_model_invocation_logs_provider",
        table_name="model_invocation_logs",
    )
    op.drop_index(
        "ix_model_invocation_logs_conversation_id",
        table_name="model_invocation_logs",
    )
    op.drop_index(
        "ix_workflow_event_logs_workflow_type",
        table_name="workflow_event_logs",
    )
    op.drop_index(
        "ix_workflow_event_logs_session_id",
        table_name="workflow_event_logs",
    )
    op.drop_index(
        "ix_message_event_logs_channel",
        table_name="message_event_logs",
    )
    op.drop_index(
        "ix_message_event_logs_session_id",
        table_name="message_event_logs",
    )
    op.drop_index(
        "ix_conversation_bindings_lookup",
        table_name="conversation_bindings",
    )
