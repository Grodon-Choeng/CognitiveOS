from typing import Protocol

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.memory.commands import CreateMemoryCommand
from app.application.memory.dto import MemoryDTO

MEMORY_PREFIXES = ("记住", "记一下", "记下", "memo")


class MemoryCreator(Protocol):
    async def create_memory(self, command: CreateMemoryCommand) -> MemoryDTO: ...


class MemoryConversationHandler:
    name = "memory"

    def __init__(self, memory_service: MemoryCreator) -> None:
        self.memory_service = memory_service

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult | None:
        memory_content = _extract_memory_content(command)
        if memory_content is None:
            return None

        await self.memory_service.create_memory(
            CreateMemoryCommand(
                content=memory_content,
                conversation_id=conversation_id,
                session_id=session_id,
                source_channel=command.channel,
                source_user_id=command.user_identity,
                source_chat_id=command.chat_id,
                source_thread_id=command.thread_id,
            )
        )
        return ConversationInboundResult(
            handled=True,
            conversation_id=conversation_id,
            session_id=session_id,
            handled_by=self.name,
            reason="memory_created",
        )


def _extract_memory_content(command: HandleInboundConversationMessageCommand) -> str | None:
    if command.message_type != "text" or command.text is None:
        return None

    normalized_text = command.text.strip()
    if not normalized_text:
        return None

    lowered_text = normalized_text.casefold()
    for prefix in MEMORY_PREFIXES:
        if lowered_text == prefix:
            return None
        if lowered_text.startswith(prefix.casefold()):
            candidate = normalized_text[len(prefix) :].lstrip("：: \n\t")
            if candidate:
                return candidate
    return None
