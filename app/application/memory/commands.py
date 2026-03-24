from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class CreateMemoryCommand:
    content: str
    memory_type: str | None = None
    conversation_id: str | None = None
    session_id: str | None = None
    source_channel: str | None = None
    source_user_id: str | None = None
    source_chat_id: str | None = None
    source_thread_id: str | None = None
    scope_object_type: str | None = None
    scope_object_id: str | None = None
    importance: int = 3
    expires_at: datetime | None = None


@dataclass(slots=True, frozen=True)
class ArchiveMemoryCommand:
    memory_id: str
