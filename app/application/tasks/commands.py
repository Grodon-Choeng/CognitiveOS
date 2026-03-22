from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class CreateTaskCommand:
    title: str
    conversation_id: str | None = None
    session_id: str | None = None
    source_channel: str | None = None
    source_user_id: str | None = None
    source_chat_id: str | None = None
    source_thread_id: str | None = None


@dataclass(slots=True, frozen=True)
class CompleteTaskCommand:
    task_id: str
