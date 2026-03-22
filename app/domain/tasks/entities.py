from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.tasks.value_objects import TaskId


class TaskStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELED = "canceled"


@dataclass(slots=True)
class Task:
    task_id: TaskId
    title: str
    created_at: datetime
    status: TaskStatus = TaskStatus.PENDING
    conversation_id: str | None = None
    session_id: str | None = None
    completed_at: datetime | None = None
