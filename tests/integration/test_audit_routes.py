from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.api.http.deps.services import get_audit_service
from app.application.audit.dto import AuditEventDTO
from app.main import app


@dataclass
class FakeAuditService:
    async def list_events(
        self,
        *,
        kind: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[AuditEventDTO]:
        _ = (kind, conversation_id, session_id, limit)
        return [
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
        ]


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
    assert response.json() == [
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
    ]
