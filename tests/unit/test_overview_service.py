from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.application.audit.dto import AuditEventDTO, AuditEventPageDTO
from app.application.memory.dto import MemoryDTO, MemoryListDTO
from app.application.overview.queries import GetOverviewQuery
from app.application.overview.service import OverviewApplicationService
from app.application.reminders.dto import ReminderDTO, ReminderListDTO
from app.application.tasks.dto import TaskDTO, TaskListDTO


@dataclass
class FakeReminderService:
    async def list_reminders(self, query: object) -> ReminderListDTO:
        _ = query
        return ReminderListDTO(
            items=[
                ReminderDTO(
                    reminder_id="r-1",
                    text="早上九点打卡",
                    remind_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
                    timezone="Asia/Shanghai",
                    status="pending",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    workflow_id="reminder:r-1",
                )
            ]
        )


@dataclass
class FakeTaskService:
    async def list_tasks(self, query: object) -> TaskListDTO:
        _ = query
        return TaskListDTO(
            items=[
                TaskDTO(
                    task_id="t-1",
                    title="整理会议纪要",
                    created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
                    status="pending",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    completed_at=None,
                )
            ]
        )


@dataclass
class FakeMemoryService:
    async def list_memories(self, query: object) -> MemoryListDTO:
        _ = query
        return MemoryListDTO(
            items=[
                MemoryDTO(
                    memory_id="m-1",
                    content="用户喜欢早上九点提醒",
                    created_at=datetime(2026, 3, 22, 8, 0, tzinfo=UTC),
                    status="active",
                    memory_type="note",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    archived_at=None,
                )
            ]
        )


@dataclass
class FakeAuditService:
    async def list_timeline(
        self,
        *,
        conversation_id: str | None = None,
        session_id: str | None = None,
        success: bool | None = None,
        channel: str | None = None,
        provider: str | None = None,
        tool_name: str | None = None,
        workflow_type: str | None = None,
        recorded_after: object | None = None,
        recorded_before: object | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditEventPageDTO:
        _ = (
            conversation_id,
            session_id,
            success,
            channel,
            provider,
            tool_name,
            workflow_type,
            recorded_after,
            recorded_before,
            cursor,
            limit,
        )
        return AuditEventPageDTO(
            items=[
                AuditEventDTO(
                    kind="message",
                    event_id="evt-1",
                    recorded_at="2026-03-22T10:00:00+00:00",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    trace_id=None,
                    chain_id=None,
                    request_id=None,
                    success=True,
                    summary="inbound:feishu:text",
                    payload={"text": "你好"},
                )
            ]
        )


@pytest.mark.asyncio
async def test_overview_service_aggregates_sections() -> None:
    service = OverviewApplicationService(
        reminder_service=FakeReminderService(),
        task_service=FakeTaskService(),
        memory_service=FakeMemoryService(),
        audit_service=FakeAuditService(),
    )

    result = await service.get_overview(
        GetOverviewQuery(
            conversation_id="conversation-1",
            session_id="session-1",
            reminder_limit=5,
            task_limit=5,
            memory_limit=5,
        )
    )

    assert result.conversation_id == "conversation-1"
    assert result.session_id == "session-1"
    assert result.pending_reminders[0].reminder_id == "r-1"
    assert result.pending_tasks[0].task_id == "t-1"
    assert result.active_memories[0].memory_id == "m-1"
    assert result.recent_activity[0].event_id == "evt-1"


@pytest.mark.asyncio
async def test_get_today_view_filters_reminders_by_local_day() -> None:
    service = OverviewApplicationService(
        reminder_service=FakeReminderService(),
        task_service=FakeTaskService(),
        memory_service=FakeMemoryService(),
        audit_service=FakeAuditService(),
    )

    result = await service.get_today_view(
        GetOverviewQuery(
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )

    assert result.pending_tasks[0].task_id == "t-1"
    assert all(reminder.timezone == "Asia/Shanghai" for reminder in result.pending_reminders)
