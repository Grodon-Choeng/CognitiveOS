from datetime import UTC, datetime

from app.application.audit.service import (
    _resolve_audit_kind_order,
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


def test_timeline_kind_order_is_explicit_and_stable() -> None:
    assert _resolve_audit_kind_order("workflow") > _resolve_audit_kind_order("tool")
    assert _resolve_audit_kind_order("tool") > _resolve_audit_kind_order("model")
    assert _resolve_audit_kind_order("model") > _resolve_audit_kind_order("message")
