from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.http.deps.services import get_reminder_service
from app.application.reminders.commands import (
    CancelReminderCommand,
    CreateReminderCommand,
    HandleReminderReplyCommand,
)
from app.application.reminders.dto import ReminderDTO, ReminderListDTO, ReminderReplyDTO
from app.application.reminders.errors import ReminderWorkflowCancelError, ReminderWorkflowStartError
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

    async def get_reminder(self, reminder_id: str) -> ReminderDTO:
        _ = reminder_id
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

    async def list_reminders(self, query: object) -> ReminderListDTO:
        _ = query
        return ReminderListDTO(
            items=[
                ReminderDTO(
                    reminder_id="00000000-0000-0000-0000-000000000001",
                    text="明天上午九点提醒我打卡",
                    remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                    timezone="Asia/Shanghai",
                    status="pending",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    workflow_id="reminder:00000000-0000-0000-0000-000000000001",
                ),
                ReminderDTO(
                    reminder_id="00000000-0000-0000-0000-000000000002",
                    text="晚上提醒我复盘",
                    remind_at=datetime(2026, 3, 20, 12, 0, tzinfo=UTC),
                    timezone="Asia/Shanghai",
                    status="completed",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    workflow_id="reminder:00000000-0000-0000-0000-000000000002",
                ),
            ]
        )

    async def handle_reply(self, command: HandleReminderReplyCommand) -> ReminderReplyDTO:
        _ = command
        return ReminderReplyDTO(
            reminder_id="00000000-0000-0000-0000-000000000001",
            reply_text="我已经处理好了",
            accepted=True,
            status="completed",
        )

    async def cancel_reminder(self, command: CancelReminderCommand) -> ReminderDTO:
        _ = command
        return ReminderDTO(
            reminder_id="00000000-0000-0000-0000-000000000001",
            text="明天上午九点提醒我打卡",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            status="canceled",
            conversation_id="conversation-1",
            session_id="session-1",
            workflow_id="reminder:00000000-0000-0000-0000-000000000001",
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

    async def get_reminder(self, reminder_id: str) -> ReminderDTO:
        _ = reminder_id
        raise AssertionError("本测试不应调用 get_reminder")

    async def list_reminders(self, query: object) -> ReminderListDTO:
        _ = query
        raise AssertionError("本测试不应调用 list_reminders")

    async def cancel_reminder(self, command: CancelReminderCommand) -> ReminderDTO:
        _ = command
        raise ReminderWorkflowCancelError("提醒工作流取消失败：RuntimeError: Temporal 不可用")


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


def test_get_reminder_route_returns_structured_response() -> None:
    app.dependency_overrides[get_reminder_service] = override_reminder_service

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/reminders/00000000-0000-0000-0000-000000000001")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


def test_list_reminders_route_returns_structured_response() -> None:
    app.dependency_overrides[get_reminder_service] = override_reminder_service

    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/reminders",
                params={"conversation_id": "conversation-1", "status": "pending", "limit": "10"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert response.json()["items"][0]["reminder_id"] == "00000000-0000-0000-0000-000000000001"


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


def test_cancel_reminder_route_returns_structured_response() -> None:
    app.dependency_overrides[get_reminder_service] = override_reminder_service

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/reminders/00000000-0000-0000-0000-000000000001/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"


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


def test_cancel_reminder_route_returns_503_when_workflow_cancel_fails() -> None:
    app.dependency_overrides[get_reminder_service] = override_failing_reminder_service

    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/reminders/00000000-0000-0000-0000-000000000001/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "detail": "提醒工作流取消失败：RuntimeError: Temporal 不可用",
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
