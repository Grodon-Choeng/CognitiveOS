from datetime import UTC, datetime

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.memory.commands import CreateMemoryCommand
from app.application.memory.conversation_handler import MemoryConversationHandler
from app.application.memory.dto import MemoryDTO


class FakeMemoryService:
    def __init__(self) -> None:
        self.created_contents: list[str] = []

    async def create_memory(self, command: CreateMemoryCommand) -> MemoryDTO:
        content = command.content
        self.created_contents.append(content)
        return MemoryDTO(
            memory_id="00000000-0000-0000-0000-000000000001",
            content=content,
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            conversation_id="conversation-1",
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_memory_conversation_handler_creates_memory_from_prefix() -> None:
    service = FakeMemoryService()
    handler = MemoryConversationHandler(service)

    result = await handler.handle(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="记住：我喜欢早上九点提醒",
            raw_payload={"text": "记住：我喜欢早上九点提醒"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled is True
    assert result.reason == "memory_created"
    assert service.created_contents == ["我喜欢早上九点提醒"]


@pytest.mark.asyncio
async def test_memory_conversation_handler_ignores_non_matching_text() -> None:
    service = FakeMemoryService()
    handler = MemoryConversationHandler(service)

    result = await handler.handle(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="这不是记忆口令",
            raw_payload={"text": "这不是记忆口令"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is None
    assert service.created_contents == []
