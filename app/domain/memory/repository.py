from typing import Protocol

from app.domain.memory.entities import MemoryEntry
from app.domain.memory.value_objects import MemoryId


class MemoryRepository(Protocol):
    async def add(self, memory: MemoryEntry) -> None: ...

    async def get(self, memory_id: MemoryId) -> MemoryEntry | None: ...

    async def list(
        self,
        *,
        conversation_id: str | None = None,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[MemoryEntry]: ...
