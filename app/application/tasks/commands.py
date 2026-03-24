from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CreateTaskCommand:
    title: str
    linked_reminder_id: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    conversation_id: str | None = None
    session_id: str | None = None
    source_channel: str | None = None
    source_user_id: str | None = None
    source_chat_id: str | None = None
    source_thread_id: str | None = None


@dataclass(slots=True, frozen=True)
class CompleteTaskCommand:
    task_id: str


@dataclass(slots=True, frozen=True)
class CancelTaskCommand:
    task_id: str
