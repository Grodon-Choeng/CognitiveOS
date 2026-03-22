from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.memory.value_objects import MemoryId


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(slots=True)
class MemoryEntry:
    memory_id: MemoryId
    content: str
    created_at: datetime
    status: MemoryStatus = MemoryStatus.ACTIVE
    conversation_id: str | None = None
    session_id: str | None = None
    archived_at: datetime | None = None
