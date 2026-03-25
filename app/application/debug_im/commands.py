from dataclasses import dataclass, field

from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class SendDebugIMMessageCommand:
    user_identity: str
    text: str
    chat_id: str | None = None
    thread_id: str | None = None
    reply_to_message_id: str | None = None
    raw_payload: JSONObject = field(default_factory=dict)
