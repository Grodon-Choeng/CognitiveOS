from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class MemoryDTO:
    memory_id: str
    content: str
    created_at: datetime
    status: str
    memory_type: str = "note"
    conversation_id: str | None = None
    session_id: str | None = None
    scope_object_type: str | None = None
    scope_object_id: str | None = None
    importance: int = 3
    expires_at: datetime | None = None
    archived_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class MemoryListDTO:
    items: list[MemoryDTO]
