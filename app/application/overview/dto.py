from dataclasses import dataclass

from app.application.audit.dto import AuditEventDTO
from app.application.memory.dto import MemoryDTO
from app.application.reminders.dto import ReminderDTO
from app.application.tasks.dto import TaskDTO


@dataclass(slots=True, frozen=True)
class OverviewDTO:
    conversation_id: str | None
    session_id: str | None
    pending_reminders: list[ReminderDTO]
    pending_tasks: list[TaskDTO]
    active_memories: list[MemoryDTO]
    recent_activity: list[AuditEventDTO]
