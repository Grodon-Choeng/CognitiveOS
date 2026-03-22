from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.http.deps.services import get_reminder_service
from app.application.reminders.commands import CreateReminderCommand, HandleReminderReplyCommand
from app.application.reminders.dto import ReminderDTO, ReminderReplyDTO
from app.application.reminders.errors import ReminderWorkflowStartError
from app.main import app

captured_create_commands: list[CreateReminderCommand] = []


@dataclass
class FakeReminderService:
    async def create_reminder(self, command: CreateReminderCommand) -> ReminderDTO:
        captured_create_commands.append(command)
        return ReminderDTO(
            reminder_id="00000000-0000-0000-0000-000000000001",
            text="明天上午九点提醒我打卡",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            status="pending",
            conversation_id="conversation-1",
            session_id="session-1",
            workflow_id="reminder:00000000-0000-0000-0000-000000000001",
        )

    async def handle_reply(self, command: HandleReminderReplyCommand) -> ReminderReplyDTO:
        _ = command
        return ReminderReplyDTO(
            reminder_id="00000000-0000-0000-0000-000000000001",
            reply_text="我已经处理好了",
            accepted=True,
            status="completed",
        )


def override_reminder_service() -> FakeReminderService:
    return FakeReminderService()


@dataclass
class FakeFailingReminderService:
    async def create_reminder(self, command: CreateReminderCommand) -> ReminderDTO:
        _ = command
        raise ReminderWorkflowStartError("提醒工作流启动失败：RuntimeError: Temporal 不可用")

    async def handle_reply(self, command: HandleReminderReplyCommand) -> ReminderReplyDTO:
        _ = command
        raise AssertionError("本测试不应调用 handle_reply")


def override_failing_reminder_service() -> FakeFailingReminderService:
    return FakeFailingReminderService()


def test_create_reminder_route_returns_structured_response() -> None:
    captured_create_commands.clear()
    app.dependency_overrides[get_reminder_service] = override_reminder_service

    try:
        with TestClient(app) as client:
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
        "conversation_id": "conversation-1",
        "session_id": "session-1",
        "workflow_id": "reminder:00000000-0000-0000-0000-000000000001",
    }


def test_create_reminder_route_passes_dispatch_chat_and_thread_fields() -> None:
    captured_create_commands.clear()
    app.dependency_overrides[get_reminder_service] = override_reminder_service

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/reminders",
                json={
                    "text": "群聊线程里提醒我打卡",
                    "remind_at": "2026-03-20T09:00:00+08:00",
                    "timezone": "Asia/Shanghai",
                    "dispatch_channel": "feishu",
                    "dispatch_recipient_id": "ou_123",
                    "dispatch_chat_id": "oc_group_123",
                    "dispatch_thread_id": "ot_thread_123",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    command = captured_create_commands[-1]
    assert command.dispatch_channel == "feishu"
    assert command.dispatch_recipient_id == "ou_123"
    assert command.dispatch_chat_id == "oc_group_123"
    assert command.dispatch_thread_id == "ot_thread_123"


def test_reply_reminder_route_returns_structured_response() -> None:
    app.dependency_overrides[get_reminder_service] = override_reminder_service

    try:
        with TestClient(app) as client:
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


def test_create_reminder_route_returns_503_when_workflow_start_fails() -> None:
    app.dependency_overrides[get_reminder_service] = override_failing_reminder_service

    try:
        with TestClient(app) as client:
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

    assert response.status_code == 503
    assert response.json() == {
        "detail": "提醒工作流启动失败：RuntimeError: Temporal 不可用",
    }


def test_create_reminder_route_rejects_dispatch_thread_without_chat() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/reminders",
            json={
                "text": "群聊线程里提醒我打卡",
                "remind_at": "2026-03-20T09:00:00+08:00",
                "timezone": "Asia/Shanghai",
                "dispatch_thread_id": "ot_thread_123",
            },
        )

    assert response.status_code == 422


def test_create_reminder_route_rejects_source_thread_without_chat() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/reminders",
            json={
                "text": "来源线程不完整",
                "remind_at": "2026-03-20T09:00:00+08:00",
                "timezone": "Asia/Shanghai",
                "source_thread_id": "source_thread_123",
            },
        )

    assert response.status_code == 422


def test_create_reminder_route_rejects_naive_remind_at() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/reminders",
            json={
                "text": "时间缺少时区",
                "remind_at": "2026-03-20T09:00:00",
                "timezone": "Asia/Shanghai",
            },
        )

    assert response.status_code == 422
