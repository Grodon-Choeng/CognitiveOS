from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class GetReminderQuery:
    reminder_id: str


@dataclass(slots=True, frozen=True)
class ListRemindersQuery:
    conversation_id: str | None = None
    session_id: str | None = None
    status: str | None = None
    limit: int = 20
