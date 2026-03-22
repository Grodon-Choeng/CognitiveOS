from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ConversationInboundResult:
    handled: bool
    conversation_id: str
    session_id: str
    handled_by: str | None = None
    reason: str | None = None
    response_text: str | None = None
