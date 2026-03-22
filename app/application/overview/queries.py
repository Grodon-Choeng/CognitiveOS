from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class GetOverviewQuery:
    conversation_id: str | None = None
    session_id: str | None = None
    reminder_limit: int = 5
    task_limit: int = 5
    memory_limit: int = 5
