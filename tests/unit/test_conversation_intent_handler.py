from datetime import UTC, datetime

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.intent_handler import (
    ConversationIntent,
    IntentConversationHandler,
    LLMFirstConversationIntentClassifier,
)
from app.application.memory.commands import CreateMemoryCommand
from app.application.memory.dto import MemoryDTO
from app.application.tasks.commands import CreateTaskCommand
from app.application.tasks.dto import TaskDTO
from app.infrastructure.llm.models import GenerateRequest, GenerateResult


class FakeLLMGateway:
    def __init__(self, content: str) -> None:
        self.content = content

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        _ = request
        return GenerateResult(
            content=self.content,
            model="gpt-test",
            provider="openai",
        )


class FailingLLMGateway:
    async def generate(self, request: GenerateRequest) -> GenerateResult:
        _ = request
        raise RuntimeError("模型不可用")


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
            completed_at=None,
        )


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
async def test_intent_classifier_prefers_llm_result() -> None:
    classifier = LLMFirstConversationIntentClassifier(
        llm_gateway=FakeLLMGateway('{"intent":"task_create","content":"买牛奶"}'),
        model="gpt-test",
        api_key_suffix="90abcdef",
    )

    result = await classifier.classify(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="帮我买牛奶",
            raw_payload={"text": "帮我买牛奶"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.TASK_CREATE
    assert result.content == "买牛奶"
    assert result.source == "llm"


@pytest.mark.asyncio
async def test_intent_classifier_falls_back_to_rules_when_llm_fails() -> None:
    classifier = LLMFirstConversationIntentClassifier(
        llm_gateway=FailingLLMGateway(),
        model="gpt-test",
        api_key_suffix="90abcdef",
    )

    result = await classifier.classify(
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

    assert result.intent == ConversationIntent.MEMORY_WRITE
    assert result.content == "我喜欢早上九点提醒"
    assert result.source == "rules"


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_task_service() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"task_create","content":"整理会议纪要"}'),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=memory_service,
    )

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
            text="帮我整理会议纪要",
            raw_payload={"text": "帮我整理会议纪要"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "task"
    assert task_service.created_titles == ["整理会议纪要"]
    assert memory_service.created_contents == []


@pytest.mark.asyncio
async def test_intent_classifier_falls_back_to_rules_when_llm_returns_unknown() -> None:
    classifier = LLMFirstConversationIntentClassifier(
        llm_gateway=FakeLLMGateway('{"intent":"unknown","content":null}'),
        model="gpt-test",
        api_key_suffix="90abcdef",
    )

    result = await classifier.classify(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="待办：整理会议纪要",
            raw_payload={"text": "待办：整理会议纪要"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.TASK_CREATE
    assert result.source == "rules"
