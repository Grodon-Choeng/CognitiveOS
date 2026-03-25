from dataclasses import dataclass
from typing import Literal

from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class ConversationInboundResult:
    handled: bool
    conversation_id: str
    session_id: str
    handled_by: str | None = None
    reason: str | None = None
    response_text: str | None = None
    debug: JSONObject | None = None


@dataclass(slots=True, frozen=True)
class ConversationFastPathResult:
    decision: Literal["completed", "needs_confirmation", "pass_to_kernel"]
    conversation_id: str
    session_id: str
    handled_by: str | None = None
    reason: str | None = None
    response_text: str | None = None
    assistant_turn_state: JSONObject | None = None
    debug: JSONObject | None = None
