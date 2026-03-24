from datetime import datetime, tzinfo
from typing import Protocol
from zoneinfo import ZoneInfo

from app.application.audit.dto import AuditEventPageDTO
from app.application.memory.dto import MemoryListDTO
from app.application.memory.queries import ListMemoriesQuery
from app.application.overview.dto import OverviewDTO
from app.application.overview.queries import GetOverviewQuery
from app.application.reminders.dto import ReminderListDTO
from app.application.reminders.queries import ListRemindersQuery
from app.application.tasks.dto import TaskListDTO
from app.application.tasks.queries import ListTasksQuery


class ReminderOverviewReader(Protocol):
    async def list_reminders(self, query: ListRemindersQuery) -> ReminderListDTO: ...


class TaskOverviewReader(Protocol):
    async def list_tasks(self, query: ListTasksQuery) -> TaskListDTO: ...


class MemoryOverviewReader(Protocol):
    async def list_memories(self, query: ListMemoriesQuery) -> MemoryListDTO: ...


class ActivityOverviewReader(Protocol):
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
        recorded_after: datetime | None = None,
        recorded_before: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditEventPageDTO: ...


class OverviewApplicationService:
    def __init__(
        self,
        *,
        reminder_service: ReminderOverviewReader,
        task_service: TaskOverviewReader,
        memory_service: MemoryOverviewReader,
        audit_service: ActivityOverviewReader,
    ) -> None:
        self.reminder_service = reminder_service
        self.task_service = task_service
        self.memory_service = memory_service
        self.audit_service = audit_service

    async def get_overview(self, query: GetOverviewQuery) -> OverviewDTO:
        reminder_list = await self.reminder_service.list_reminders(
            ListRemindersQuery(
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                status="pending",
                limit=query.reminder_limit,
            )
        )
        task_list = await self.task_service.list_tasks(
            ListTasksQuery(
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                status="pending",
                limit=query.task_limit,
            )
        )
        memory_list = await self.memory_service.list_memories(
            ListMemoriesQuery(
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                status="active",
                limit=query.memory_limit,
            )
        )
        activity_page = await self.audit_service.list_timeline(
            conversation_id=query.conversation_id,
            session_id=query.session_id,
            limit=query.recent_activity_limit,
        )
        return OverviewDTO(
            conversation_id=query.conversation_id,
            session_id=query.session_id,
            pending_reminders=reminder_list.items,
            pending_tasks=task_list.items,
            active_memories=memory_list.items,
            recent_activity=activity_page.items,
        )

    async def get_today_view(self, query: GetOverviewQuery) -> OverviewDTO:
        overview = await self.get_overview(query)
        now = datetime.now().astimezone()
        today_reminders = [
            reminder
            for reminder in overview.pending_reminders
            if _is_same_local_day(reminder.remind_at, reminder.timezone, now)
        ]
        return OverviewDTO(
            conversation_id=overview.conversation_id,
            session_id=overview.session_id,
            pending_reminders=today_reminders,
            pending_tasks=overview.pending_tasks,
            active_memories=overview.active_memories,
            recent_activity=overview.recent_activity,
        )

    async def get_working_set_view(self, query: GetOverviewQuery) -> OverviewDTO:
        return await self.get_overview(query)


def _is_same_local_day(
    remind_at: datetime,
    timezone: str,
    now: datetime,
) -> bool:
    zone: tzinfo | None
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        if now.tzinfo is None:
            return remind_at.date() == now.date()
        zone = now.tzinfo
    if zone is None:
        return remind_at.date() == now.date()
    return remind_at.astimezone(zone).date() == now.astimezone(zone).date()
