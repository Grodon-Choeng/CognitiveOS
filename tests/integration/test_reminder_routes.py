from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.http.deps.services import get_reminder_service
from app.application.reminders.dto import ReminderDTO, ReminderReplyDTO
from app.main import app


@dataclass
class FakeReminderService:
    async def create_reminder(self, command: object) -> ReminderDTO:
        _ = command
        return ReminderDTO(
            reminder_id="00000000-0000-0000-0000-000000000001",
            text="明天上午九点提醒我打卡",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            status="pending",
            workflow_id="reminder:00000000-0000-0000-0000-000000000001",
        )

    async def handle_reply(self, command: object) -> ReminderReplyDTO:
        _ = command
        return ReminderReplyDTO(
            reminder_id="00000000-0000-0000-0000-000000000001",
            reply_text="我已经处理好了",
            accepted=True,
            status="completed",
        )


def test_create_reminder_route_returns_structured_response() -> None:
    client = TestClient(app)
    app.dependency_overrides[get_reminder_service] = lambda: FakeReminderService()

    try:
        response = client.post(
            "/api/v1/reminders",
            json={
                "text": "明天上午九点提醒我打卡",
                "remind_at": "2026-03-20T09:00:00+08:00",
                "timezone": "Asia/Shanghai",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "reminder_id": "00000000-0000-0000-0000-000000000001",
        "text": "明天上午九点提醒我打卡",
        "remind_at": "2026-03-20T09:00:00Z",
        "timezone": "Asia/Shanghai",
        "status": "pending",
        "workflow_id": "reminder:00000000-0000-0000-0000-000000000001",
    }


def test_reply_reminder_route_returns_structured_response() -> None:
    client = TestClient(app)
    app.dependency_overrides[get_reminder_service] = lambda: FakeReminderService()

    try:
        response = client.post(
            "/api/v1/reminders/00000000-0000-0000-0000-000000000001/reply",
            json={"reply_text": "我已经处理好了"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "reminder_id": "00000000-0000-0000-0000-000000000001",
        "reply_text": "我已经处理好了",
        "accepted": True,
        "status": "completed",
    }
