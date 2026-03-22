from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class GetTaskQuery:
    task_id: str


@dataclass(slots=True, frozen=True)
class ListTasksQuery:
    conversation_id: str | None = None
    session_id: str | None = None
    status: str | None = None
    query: str | None = None
    limit: int = 20
