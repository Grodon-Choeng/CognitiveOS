from typing import Protocol

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


class OverviewApplicationService:
    def __init__(
        self,
        *,
        reminder_service: ReminderOverviewReader,
        task_service: TaskOverviewReader,
        memory_service: MemoryOverviewReader,
    ) -> None:
        self.reminder_service = reminder_service
        self.task_service = task_service
        self.memory_service = memory_service

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
        return OverviewDTO(
            conversation_id=query.conversation_id,
            session_id=query.session_id,
            pending_reminders=reminder_list.items,
            pending_tasks=task_list.items,
            active_memories=memory_list.items,
        )
