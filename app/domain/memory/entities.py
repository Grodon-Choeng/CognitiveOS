from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.memory.value_objects import MemoryId


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class MemoryType(StrEnum):
    NOTE = "note"
    PREFERENCE = "preference"
    CONTEXT = "context"
    TEMPORARY = "temporary"


@dataclass(slots=True)
class MemoryEntry:
    memory_id: MemoryId
    content: str
    created_at: datetime
    status: MemoryStatus = MemoryStatus.ACTIVE
    memory_type: MemoryType = MemoryType.NOTE
    conversation_id: str | None = None
    session_id: str | None = None
    scope_object_type: str | None = None
    scope_object_id: str | None = None
    importance: int = 3
    expires_at: datetime | None = None
    archived_at: datetime | None = None
