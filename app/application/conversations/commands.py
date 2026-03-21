from dataclasses import dataclass

from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class HandleInboundConversationMessageCommand:
    channel: str
    message_type: str
    user_identity: str
    external_message_id: str | None
    root_message_id: str | None
    parent_message_id: str | None
    chat_id: str | None
    thread_id: str | None
    text: str | None
    raw_payload: JSONObject
