from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ListDebugIMMessagesQuery:
    user_identity: str
    chat_id: str | None = None
    thread_id: str | None = None
    limit: int = 50


@dataclass(slots=True, frozen=True)
class PollDebugIMMessagesQuery:
    user_identity: str
    chat_id: str | None = None
    thread_id: str | None = None
    after_recorded_at: str | None = None
    after_event_id: str | None = None
    limit: int = 100


@dataclass(slots=True, frozen=True)
class ListDebugIMSessionsQuery:
    user_identity: str | None = None
    limit: int = 20
