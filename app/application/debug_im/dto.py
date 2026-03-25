from dataclasses import dataclass, field

from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class DebugIMMessageDTO:
    event_id: str
    recorded_at: str
    direction: str
    channel: str
    user_identity: str | None
    chat_id: str | None
    thread_id: str | None
    conversation_id: str | None
    session_id: str | None
    external_message_id: str | None
    root_message_id: str | None
    parent_message_id: str | None
    text: str | None
    success: bool
    adapter_name: str | None = None
    metadata: JSONObject = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class DebugIMMessageListDTO:
    items: list[DebugIMMessageDTO]


@dataclass(slots=True, frozen=True)
class DebugIMSessionDTO:
    session_key: str
    user_identity: str
    chat_id: str | None
    thread_id: str | None
    conversation_id: str | None
    session_id: str | None
    last_message_at: str
    last_message_direction: str
    last_message_text: str | None
    last_external_message_id: str | None


@dataclass(slots=True, frozen=True)
class DebugIMSessionListDTO:
    items: list[DebugIMSessionDTO]


@dataclass(slots=True, frozen=True)
class DebugIMSendMessageDTO:
    accepted: bool
    conversation_id: str
    session_id: str
    message_id: str
    handled: bool
    handled_by: str | None = None
    reason: str | None = None
    response_text: str | None = None
