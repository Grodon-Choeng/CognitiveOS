from typing import cast

from sqlalchemy import Table

from app.infrastructure.db.models.conversation_binding import ConversationBindingModel
from app.infrastructure.db.models.message_event import MessageEventLogModel
from app.infrastructure.db.models.model_invocation import ModelInvocationLogModel
from app.infrastructure.db.models.reminder import ReminderModel
from app.infrastructure.db.models.tool_invocation import ToolInvocationLogModel
from app.infrastructure.db.models.workflow_event import WorkflowEventLogModel


def test_conversation_binding_model_declares_lookup_index() -> None:
    table = cast(Table, ConversationBindingModel.__table__)
    index_map = {str(index.name): index for index in table.indexes}

    assert "ux_conversation_bindings_source" in index_map
    assert index_map["ux_conversation_bindings_source"].unique is True


def test_audit_models_declare_hot_path_indexes() -> None:
    message_table = cast(Table, MessageEventLogModel.__table__)
    workflow_table = cast(Table, WorkflowEventLogModel.__table__)
    model_table = cast(Table, ModelInvocationLogModel.__table__)
    tool_table = cast(Table, ToolInvocationLogModel.__table__)

    message_index_names = {index.name for index in message_table.indexes}
    workflow_index_names = {index.name for index in workflow_table.indexes}
    model_index_names = {index.name for index in model_table.indexes}
    tool_index_names = {index.name for index in tool_table.indexes}

    assert "ix_message_event_logs_session_id" in message_index_names
    assert "ix_message_event_logs_channel" in message_index_names
    assert "ix_workflow_event_logs_session_id" in workflow_index_names
    assert "ix_workflow_event_logs_workflow_type" in workflow_index_names
    assert "ix_model_invocation_logs_conversation_id" in model_index_names
    assert "ix_model_invocation_logs_provider" in model_index_names
    assert "ix_tool_invocation_logs_conversation_id" in tool_index_names


def test_reminder_model_declares_lookup_indexes() -> None:
    reminder_table = cast(Table, ReminderModel.__table__)
    reminder_index_names = {str(index.name) for index in reminder_table.indexes}

    assert "ix_reminders_pending_conversation_lookup" in reminder_index_names
    assert "ix_reminders_pending_dispatch_lookup" in reminder_index_names
    assert "ix_reminders_pending_dispatch_chat_lookup" in reminder_index_names
