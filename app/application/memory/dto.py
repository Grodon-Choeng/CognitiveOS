from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class MemoryDTO:
    memory_id: str
    content: str
    created_at: datetime
    conversation_id: str | None = None
    session_id: str | None = None


@dataclass(slots=True, frozen=True)
class MemoryListDTO:
    items: list[MemoryDTO]
