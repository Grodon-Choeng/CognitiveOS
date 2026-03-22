from datetime import UTC, datetime

from app.application.audit.dto import AuditEventDTO
from app.application.audit.service import (
    _build_timeline_sort_key,
    decode_audit_cursor,
    encode_audit_cursor,
)


def test_timeline_cursor_roundtrip_keeps_kind() -> None:
    cursor = encode_audit_cursor(
        recorded_at=datetime(2026, 3, 22, 12, 0, tzinfo=UTC),
        event_id="evt_1",
        kind="tool",
    )
    decoded = decode_audit_cursor(cursor)

    assert decoded.kind == "tool"


def test_timeline_sort_key_is_stable_for_same_timestamp() -> None:
    same_time = "2026-03-22T12:00:00+00:00"
    items = [
        AuditEventDTO(
            kind="message",
            event_id="z",
            recorded_at=same_time,
            conversation_id=None,
            session_id=None,
            trace_id=None,
            chain_id=None,
            request_id=None,
            success=True,
            summary="message",
        ),
        AuditEventDTO(
            kind="workflow",
            event_id="a",
            recorded_at=same_time,
            conversation_id=None,
            session_id=None,
            trace_id=None,
            chain_id=None,
            request_id=None,
            success=True,
            summary="workflow",
        ),
    ]

    ordered = sorted(items, key=_build_timeline_sort_key, reverse=True)

    assert [item.kind for item in ordered] == ["workflow", "message"]
