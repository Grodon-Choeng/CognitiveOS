from datetime import UTC, datetime

from app.application.audit.service import decode_audit_cursor, encode_audit_cursor


def test_audit_cursor_roundtrip() -> None:
    cursor = encode_audit_cursor(
        recorded_at=datetime(2026, 3, 21, 12, 0, tzinfo=UTC),
        event_id="evt_1",
    )
    decoded = decode_audit_cursor(cursor)

    assert decoded.recorded_at == "2026-03-21T12:00:00+00:00"
    assert decoded.event_id == "evt_1"
