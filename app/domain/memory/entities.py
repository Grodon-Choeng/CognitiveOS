from dataclasses import dataclass
from datetime import datetime

from app.domain.memory.value_objects import MemoryId


@dataclass(slots=True)
class MemoryEntry:
    memory_id: MemoryId
    content: str
    created_at: datetime
    conversation_id: str | None = None
    session_id: str | None = None
