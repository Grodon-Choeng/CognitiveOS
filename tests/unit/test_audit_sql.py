from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.application.audit.service import _apply_common_filters, encode_audit_cursor
from app.infrastructure.db.models.message_event import MessageEventLogModel


def test_timeline_cursor_filter_uses_kind_aware_condition() -> None:
    cursor = encode_audit_cursor(
        recorded_at=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
        event_id="evt_cursor",
        kind="tool",
    )
    statement = _apply_common_filters(
        statement=select(MessageEventLogModel),
        conversation_column=MessageEventLogModel.conversation_id,
        session_column=MessageEventLogModel.session_id,
        success_column=MessageEventLogModel.success,
        recorded_at_column=MessageEventLogModel.recorded_at,
        event_id_column=MessageEventLogModel.event_id,
        conversation_id=None,
        session_id=None,
        success=None,
        recorded_after=None,
        recorded_before=None,
        cursor=cursor,
        timeline_kind="message",
    )

    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "'message' < 'tool'" in compiled
    assert "message_event_logs.event_id < 'evt_cursor'" in compiled
