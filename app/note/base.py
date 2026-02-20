from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any


class NoteType(str, Enum):
    REMINDER = "reminder"
    IDEA = "idea"
    NOTE = "note"
    TASK = "task"


class TaskPriority(str, Enum):
    LATER = "LATER"
    NOW = "NOW"
    DONE = "DONE"


class NoteEntry:
    def __init__(
        self,
        content: str,
        note_type: NoteType = NoteType.NOTE,
        tags: list[str] | None = None,
        remind_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        task_priority: TaskPriority = TaskPriority.LATER,
    ) -> None:
        self.content = content
        self.note_type = note_type
        self.tags = tags or []
        self.remind_at = remind_at
        self.metadata = metadata or {}
        self.task_priority = task_priority
        self.created_at = datetime.now()


class NoteAdapter(ABC):
    @abstractmethod
    async def write_daily_entry(self, entry: NoteEntry) -> str:
        pass

    @abstractmethod
    async def get_daily_path(self, date: datetime | None = None) -> str:
        pass

    @abstractmethod
    def format_entry(self, entry: NoteEntry) -> str:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def file_extension(self) -> str:
        pass
