from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class GetMemoryQuery:
    memory_id: str


@dataclass(slots=True, frozen=True)
class ListMemoriesQuery:
    conversation_id: str | None = None
    session_id: str | None = None
    status: str | None = None
    limit: int = 20
