from dataclasses import dataclass
from datetime import datetime

from fastapi.testclient import TestClient

from app.api.http.deps.services import get_audit_service
from app.application.audit.dto import AuditEventDTO, AuditEventPageDTO
from app.main import app


@dataclass
class FakeAuditService:
    async def list_events(
        self,
        *,
        kind: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        recorded_after: datetime | None = None,
        recorded_before: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditEventPageDTO:
        _ = (kind, conversation_id, session_id, recorded_after, recorded_before, cursor, limit)
        return AuditEventPageDTO(
            items=[
                AuditEventDTO(
                    kind="message",
                    event_id="evt_1",
                    recorded_at="2026-03-21T12:00:00+08:00",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    trace_id=None,
                    chain_id=None,
                    request_id=None,
                    success=True,
                    summary="inbound:web:text",
                    payload={"text": "你好"},
                )
            ],
            next_cursor="cursor_1",
        )


def override_audit_service() -> FakeAuditService:
    return FakeAuditService()


def test_audit_events_route_returns_structured_response() -> None:
    client = TestClient(app)
    app.dependency_overrides[get_audit_service] = override_audit_service

    try:
        response = client.get("/api/v1/audit/events", params={"kind": "message"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "kind": "message",
                "event_id": "evt_1",
                "recorded_at": "2026-03-21T12:00:00+08:00",
                "conversation_id": "conversation-1",
                "session_id": "session-1",
                "trace_id": None,
                "chain_id": None,
                "request_id": None,
                "success": True,
                "summary": "inbound:web:text",
                "payload": {"text": "你好"},
            }
        ],
        "next_cursor": "cursor_1",
    }
