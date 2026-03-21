from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True, frozen=True)
class ResolvedConversationContext:
    conversation_id: str
    session_id: str


class ConversationContextResolver(Protocol):
    async def resolve_for_outbound(
        self,
        *,
        provided_conversation_id: str | None,
        provided_session_id: str | None,
        source_channel: str | None,
        source_user_id: str | None,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext: ...

    async def resolve_for_inbound(
        self,
        *,
        source_channel: str,
        source_user_id: str,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext: ...
