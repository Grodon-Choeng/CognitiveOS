from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from app.application.audit.service import _build_timeline_statement, encode_audit_cursor


def test_timeline_statement_uses_union_all_and_stable_ordering() -> None:
    statement = _build_timeline_statement(
        conversation_id=None,
        session_id=None,
        success=None,
        channel=None,
        provider=None,
        tool_name=None,
        workflow_type=None,
        recorded_after=None,
        recorded_before=None,
        cursor=None,
    )

    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "UNION ALL" in compiled
    assert "ORDER BY audit_timeline.recorded_at DESC" in compiled
    assert "audit_timeline.kind_order DESC" in compiled


def test_timeline_cursor_filter_uses_kind_order_when_present() -> None:
    cursor = encode_audit_cursor(
        recorded_at=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
        event_id="evt_cursor",
        kind="tool",
    )
    statement = _build_timeline_statement(
        conversation_id=None,
        session_id=None,
        success=None,
        channel=None,
        provider=None,
        tool_name=None,
        workflow_type=None,
        recorded_after=None,
        recorded_before=None,
        cursor=cursor,
    )

    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "audit_timeline.kind_order < 3" in compiled
    assert "audit_timeline.event_id < 'evt_cursor'" in compiled
