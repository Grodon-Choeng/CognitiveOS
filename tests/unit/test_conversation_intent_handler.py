from datetime import UTC, datetime

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.intent_handler import (
    ConversationIntent,
    IntentConversationHandler,
    LLMFirstConversationIntentClassifier,
)
from app.application.memory.commands import CreateMemoryCommand
from app.application.memory.dto import MemoryDTO, MemoryListDTO
from app.application.overview.dto import OverviewDTO
from app.application.overview.queries import GetOverviewQuery
from app.application.reminders.commands import CreateReminderCommand
from app.application.reminders.dto import ReminderDTO, ReminderListDTO
from app.application.tasks.commands import CreateTaskCommand
from app.application.tasks.dto import TaskDTO, TaskListDTO
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
        self.completed_latest_calls: list[tuple[str, str]] = []
        self.canceled_latest_calls: list[tuple[str, str]] = []
        self.list_queries: list[object] = []

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

    async def complete_latest_task(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> TaskDTO:
        self.completed_latest_calls.append((conversation_id, session_id))
        return TaskDTO(
            task_id="00000000-0000-0000-0000-000000000002",
            title="最近待办",
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="completed",
            conversation_id=conversation_id,
            session_id=session_id,
            completed_at=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
        )

    async def cancel_latest_task(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> TaskDTO:
        self.canceled_latest_calls.append((conversation_id, session_id))
        return TaskDTO(
            task_id="00000000-0000-0000-0000-000000000003",
            title="最近待办",
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="canceled",
            conversation_id=conversation_id,
            session_id=session_id,
            completed_at=None,
        )

    async def list_tasks(self, query: object) -> TaskListDTO:
        self.list_queries.append(query)
        return TaskListDTO(
            items=[
                TaskDTO(
                    task_id="00000000-0000-0000-0000-000000000010",
                    title="整理纪要",
                    created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
                    status="pending",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    completed_at=None,
                )
            ]
        )


class FakeMemoryService:
    def __init__(self) -> None:
        self.created_contents: list[str] = []
        self.archived_latest_calls: list[tuple[str, str]] = []
        self.list_queries: list[object] = []

    async def create_memory(self, command: CreateMemoryCommand) -> MemoryDTO:
        content = command.content
        self.created_contents.append(content)
        return MemoryDTO(
            memory_id="00000000-0000-0000-0000-000000000001",
            content=content,
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="active",
            conversation_id="conversation-1",
            session_id="session-1",
            archived_at=None,
        )

    async def archive_latest_memory(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> MemoryDTO:
        self.archived_latest_calls.append((conversation_id, session_id))
        return MemoryDTO(
            memory_id="00000000-0000-0000-0000-000000000002",
            content="最近记忆",
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="archived",
            conversation_id=conversation_id,
            session_id=session_id,
            archived_at=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
        )

    async def list_memories(self, query: object) -> MemoryListDTO:
        self.list_queries.append(query)
        return MemoryListDTO(
            items=[
                MemoryDTO(
                    memory_id="00000000-0000-0000-0000-000000000020",
                    content="喜欢早上九点提醒",
                    created_at=datetime(2026, 3, 22, 8, 0, tzinfo=UTC),
                    status="active",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    archived_at=None,
                )
            ]
        )


class FakeReminderService:
    def __init__(self) -> None:
        self.created_requests: list[tuple[str, datetime, str]] = []
        self.canceled_latest_calls: list[tuple[str, str]] = []
        self.list_queries: list[object] = []

    async def create_reminder(self, command: CreateReminderCommand) -> ReminderDTO:
        self.created_requests.append((command.text, command.remind_at, command.timezone))
        return ReminderDTO(
            reminder_id="00000000-0000-0000-0000-000000000001",
            text=command.text,
            remind_at=command.remind_at,
            timezone=command.timezone,
            status="pending",
            conversation_id="conversation-1",
            session_id="session-1",
            workflow_id="reminder:00000000-0000-0000-0000-000000000001",
        )

    async def cancel_latest_reminder(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ReminderDTO:
        self.canceled_latest_calls.append((conversation_id, session_id))
        return ReminderDTO(
            reminder_id="00000000-0000-0000-0000-000000000004",
            text="最近提醒",
            remind_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            status="canceled",
            conversation_id=conversation_id,
            session_id=session_id,
            workflow_id="reminder:00000000-0000-0000-0000-000000000004",
        )

    async def list_reminders(self, query: object) -> ReminderListDTO:
        self.list_queries.append(query)
        return ReminderListDTO(
            items=[
                ReminderDTO(
                    reminder_id="00000000-0000-0000-0000-000000000030",
                    text="九点打卡",
                    remind_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
                    timezone="Asia/Shanghai",
                    status="pending",
                    conversation_id="conversation-1",
                    session_id="session-1",
                    workflow_id="reminder:r-30",
                )
            ]
        )


class FakeOverviewService:
    def __init__(self) -> None:
        self.queries: list[GetOverviewQuery] = []

    async def get_overview(self, query: GetOverviewQuery) -> OverviewDTO:
        self.queries.append(query)
        return OverviewDTO(
            conversation_id=query.conversation_id,
            session_id=query.session_id,
            pending_reminders=[
                ReminderDTO(
                    reminder_id="r-1",
                    text="九点打卡",
                    remind_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
                    timezone="Asia/Shanghai",
                    status="pending",
                    conversation_id=query.conversation_id,
                    session_id=query.session_id,
                    workflow_id="reminder:r-1",
                )
            ],
            pending_tasks=[
                TaskDTO(
                    task_id="t-1",
                    title="整理纪要",
                    created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
                    status="pending",
                    conversation_id=query.conversation_id,
                    session_id=query.session_id,
                    completed_at=None,
                )
            ],
            active_memories=[
                MemoryDTO(
                    memory_id="m-1",
                    content="喜欢早上九点提醒",
                    created_at=datetime(2026, 3, 22, 8, 0, tzinfo=UTC),
                    status="active",
                    conversation_id=query.conversation_id,
                    session_id=query.session_id,
                    archived_at=None,
                )
            ],
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
    assert result.remind_at is None


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
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"task_create","content":"整理会议纪要"}'),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        overview_service=overview_service,
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
    assert reminder_service.created_requests == []
    assert overview_service.queries == []


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_task_list() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"task_list","content":null}'),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        overview_service=overview_service,
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
            text="查看待办",
            raw_payload={"text": "查看待办"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "task"
    assert result.reason == "task_listed_via_llm"
    assert "当前任务：" in (result.response_text or "")
    assert task_service.list_queries


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


@pytest.mark.asyncio
async def test_intent_classifier_parses_llm_reminder_create() -> None:
    classifier = LLMFirstConversationIntentClassifier(
        llm_gateway=FakeLLMGateway(
            '{"intent":"reminder_create","content":"打卡","remind_at":"2026-03-23T09:00:00+08:00","timezone":"Asia/Shanghai"}'
        ),
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
            text="明天早上九点提醒我打卡",
            raw_payload={"text": "明天早上九点提醒我打卡"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.REMINDER_CREATE
    assert result.content == "打卡"
    assert result.timezone == "Asia/Shanghai"
    expected_remind_at = datetime.fromisoformat("2026-03-23T09:00:00+08:00")
    assert result.remind_at == expected_remind_at
    assert result.source == "llm"


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_reminder_service() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway(
                '{"intent":"reminder_create","content":"打卡","remind_at":"2026-03-23T09:00:00+08:00","timezone":"Asia/Shanghai"}'
            ),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        overview_service=overview_service,
    )

    result = await handler.handle(
        HandleInboundConversationMessageCommand(
            channel="feishu",
            message_type="text",
            user_identity="ou_123",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id="oc_123",
            thread_id=None,
            text="明天早上九点提醒我打卡",
            raw_payload={"text": "明天早上九点提醒我打卡"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "reminder"
    assert result.reason == "reminder_created_via_llm"
    assert reminder_service.created_requests[0][0] == "打卡"
    assert task_service.created_titles == []
    assert memory_service.created_contents == []


@pytest.mark.asyncio
async def test_intent_classifier_falls_back_to_structured_reminder_rule() -> None:
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
            text="提醒：2026-03-23T09:00:00+08:00 打卡",
            raw_payload={"text": "提醒：2026-03-23T09:00:00+08:00 打卡"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.REMINDER_CREATE
    assert result.content == "打卡"
    assert result.source == "rules"


@pytest.mark.asyncio
async def test_intent_classifier_supports_task_complete() -> None:
    classifier = LLMFirstConversationIntentClassifier(
        llm_gateway=FakeLLMGateway('{"intent":"task_complete","content":null}'),
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
            text="完成任务",
            raw_payload={"text": "完成任务"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.TASK_COMPLETE
    assert result.source == "llm"


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_complete_latest_task() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"task_complete","content":null}'),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        overview_service=overview_service,
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
            text="完成任务",
            raw_payload={"text": "完成任务"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "task"
    assert result.reason == "task_completed_via_llm"
    assert task_service.completed_latest_calls == [("conversation-1", "session-1")]


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_cancel_latest_task() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"task_cancel","content":null}'),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        overview_service=overview_service,
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
            text="取消任务",
            raw_payload={"text": "取消任务"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "task"
    assert result.reason == "task_canceled_via_llm"
    assert task_service.canceled_latest_calls == [("conversation-1", "session-1")]


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_archive_latest_memory() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"memory_archive","content":null}'),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        overview_service=overview_service,
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
            text="归档记忆",
            raw_payload={"text": "归档记忆"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "memory"
    assert result.reason == "memory_archived_via_llm"
    assert memory_service.archived_latest_calls == [("conversation-1", "session-1")]


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_memory_list() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"memory_list","content":null}'),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        overview_service=overview_service,
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
            text="查看记忆",
            raw_payload={"text": "查看记忆"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "memory"
    assert result.reason == "memory_listed_via_llm"
    assert "当前记忆：" in (result.response_text or "")
    assert memory_service.list_queries


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_cancel_latest_reminder() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"reminder_cancel","content":null}'),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        overview_service=overview_service,
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
            text="取消提醒",
            raw_payload={"text": "取消提醒"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "reminder"
    assert result.reason == "reminder_canceled_via_llm"
    assert reminder_service.canceled_latest_calls == [("conversation-1", "session-1")]


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_reminder_list() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"reminder_list","content":null}'),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        overview_service=overview_service,
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
            text="查看提醒",
            raw_payload={"text": "查看提醒"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "reminder"
    assert result.reason == "reminder_listed_via_llm"
    assert "当前提醒：" in (result.response_text or "")
    assert reminder_service.list_queries


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_overview_service() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"overview_show","content":null}'),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=memory_service,
        reminder_service=reminder_service,
        overview_service=overview_service,
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
            text="查看概览",
            raw_payload={"text": "查看概览"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "overview"
    assert result.reason == "overview_shown_via_llm"
    assert "当前概览：" in (result.response_text or "")
    assert overview_service.queries[0].conversation_id == "conversation-1"
