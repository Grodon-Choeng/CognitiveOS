from datetime import UTC, datetime

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.tasks.commands import CreateTaskCommand
from app.application.tasks.conversation_handler import TaskConversationHandler
from app.application.tasks.dto import TaskDTO


class FakeTaskService:
    def __init__(self) -> None:
        self.created_titles: list[str] = []

    async def create_task(self, command: CreateTaskCommand) -> TaskDTO:
        title = command.title
        self.created_titles.append(title)
        return TaskDTO(
            task_id="00000000-0000-0000-0000-000000000001",
            title=title,
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="pending",
            conversation_id="conversation-1",
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_task_conversation_handler_creates_task_from_prefix() -> None:
    service = FakeTaskService()
    handler = TaskConversationHandler(service)

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
            text="待办：整理今天的会议纪要",
            raw_payload={"text": "待办：整理今天的会议纪要"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled is True
    assert result.reason == "task_created"
    assert service.created_titles == ["整理今天的会议纪要"]


@pytest.mark.asyncio
async def test_task_conversation_handler_ignores_non_matching_text() -> None:
    service = FakeTaskService()
    handler = TaskConversationHandler(service)

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
            text="今天心情不错",
            raw_payload={"text": "今天心情不错"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is None
    assert service.created_titles == []
