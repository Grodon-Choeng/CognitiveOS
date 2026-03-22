from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class TaskDTO:
    task_id: str
    title: str
    created_at: datetime
    status: str
    conversation_id: str | None = None
    session_id: str | None = None
    completed_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class TaskListDTO:
    items: list[TaskDTO]
