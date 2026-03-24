from datetime import UTC, datetime
from typing import Any

import pytest

from app.application.audit.dto import AuditEventDTO
from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.intent_handler import (
    ConversationIntent,
    IntentConversationHandler,
    LLMFirstConversationIntentClassifier,
)
from app.application.memory.commands import CreateMemoryCommand
from app.application.memory.dto import MemoryDTO, MemoryListDTO
from app.application.memory.queries import ListMemoriesQuery
from app.application.overview.dto import OverviewDTO
from app.application.overview.queries import GetOverviewQuery
from app.application.reminders.commands import CancelReminderCommand, CreateReminderCommand
from app.application.reminders.dto import ReminderDTO, ReminderListDTO
from app.application.reminders.queries import ListRemindersQuery
from app.application.tasks.commands import CreateTaskCommand
from app.application.tasks.dto import TaskDTO, TaskListDTO
from app.application.tasks.errors import TaskNotFoundError
from app.application.tasks.queries import ListTasksQuery
from app.infrastructure.llm.models import GenerateRequest, GenerateResult


class FakeLLMGateway:
    def __init__(self, content: str) -> None:
        self.content = content
        self.last_request: GenerateRequest | None = None

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        self.last_request = request
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
        self.attached_reminders: list[tuple[str, str]] = []
        self.list_queries: list[ListTasksQuery] = []
        self.complete_latest_error: Exception | None = None

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
            linked_reminder_id=command.linked_reminder_id,
            source_type=command.source_type,
            source_id=command.source_id,
            completed_at=None,
        )

    async def get_task(self, task_id: str) -> TaskDTO:
        return TaskDTO(
            task_id=task_id,
            title="整理纪要",
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
        if self.complete_latest_error is not None:
            raise self.complete_latest_error
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

    async def complete_task(self, command: object) -> TaskDTO:
        _ = command
        return await self.complete_latest_task(
            conversation_id="conversation-1",
            session_id="session-1",
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

    async def cancel_task(self, command: object) -> TaskDTO:
        _ = command
        return await self.cancel_latest_task(
            conversation_id="conversation-1",
            session_id="session-1",
        )

    async def complete_matching_task(
        self,
        *,
        conversation_id: str,
        session_id: str,
        title_hint: str,
    ) -> TaskDTO:
        self.completed_latest_calls.append((conversation_id, session_id))
        return TaskDTO(
            task_id="00000000-0000-0000-0000-000000000011",
            title=title_hint,
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="completed",
            conversation_id=conversation_id,
            session_id=session_id,
            completed_at=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
        )

    async def cancel_matching_task(
        self,
        *,
        conversation_id: str,
        session_id: str,
        title_hint: str,
    ) -> TaskDTO:
        self.canceled_latest_calls.append((conversation_id, session_id))
        return TaskDTO(
            task_id="00000000-0000-0000-0000-000000000012",
            title=title_hint,
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="canceled",
            conversation_id=conversation_id,
            session_id=session_id,
            completed_at=None,
        )

    async def list_tasks(self, query: ListTasksQuery) -> TaskListDTO:
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

    async def attach_reminder(
        self,
        *,
        task_id: str,
        reminder_id: str,
    ) -> TaskDTO:
        self.attached_reminders.append((task_id, reminder_id))
        return TaskDTO(
            task_id=task_id,
            title="整理纪要",
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="pending",
            conversation_id="conversation-1",
            session_id="session-1",
            linked_reminder_id=reminder_id,
            completed_at=None,
        )


class FakeMemoryService:
    def __init__(self) -> None:
        self.created_contents: list[str] = []
        self.archived_latest_calls: list[tuple[str, str]] = []
        self.list_queries: list[ListMemoriesQuery] = []

    async def create_memory(self, command: CreateMemoryCommand) -> MemoryDTO:
        content = command.content
        self.created_contents.append(content)
        return MemoryDTO(
            memory_id="00000000-0000-0000-0000-000000000001",
            content=content,
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="active",
            memory_type="note",
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
            memory_type="note",
            conversation_id=conversation_id,
            session_id=session_id,
            archived_at=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
        )

    async def archive_memory(self, command: object) -> MemoryDTO:
        _ = command
        return await self.archive_latest_memory(
            conversation_id="conversation-1",
            session_id="session-1",
        )

    async def archive_matching_memory(
        self,
        *,
        conversation_id: str,
        session_id: str,
        content_hint: str,
    ) -> MemoryDTO:
        self.archived_latest_calls.append((conversation_id, session_id))
        return MemoryDTO(
            memory_id="00000000-0000-0000-0000-000000000021",
            content=content_hint,
            created_at=datetime(2026, 3, 22, 9, 0, tzinfo=UTC),
            status="archived",
            memory_type="note",
            conversation_id=conversation_id,
            session_id=session_id,
            archived_at=datetime(2026, 3, 22, 10, 0, tzinfo=UTC),
        )

    async def list_memories(self, query: ListMemoriesQuery) -> MemoryListDTO:
        self.list_queries.append(query)
        return MemoryListDTO(
            items=[
                MemoryDTO(
                    memory_id="00000000-0000-0000-0000-000000000020",
                    content="喜欢早上九点提醒",
                    created_at=datetime(2026, 3, 22, 8, 0, tzinfo=UTC),
                    status="active",
                    memory_type="note",
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
        self.linked_tasks: list[tuple[str, str]] = []
        self.retry_commands: list[str] = []
        self.cancel_commands: list[str] = []
        self.reschedule_commands: list[tuple[str, datetime, str]] = []
        self.list_queries: list[ListRemindersQuery] = []

    async def create_reminder(self, command: CreateReminderCommand) -> ReminderDTO:
        self.created_requests.append((command.text, command.remind_at, command.timezone))
        return ReminderDTO(
            reminder_id="00000000-0000-0000-0000-000000000001",
            text=command.text,
            remind_at=command.remind_at,
            timezone=command.timezone,
            status="pending",
            linked_task_id=command.linked_task_id,
            conversation_id="conversation-1",
            session_id="session-1",
            workflow_id="reminder:00000000-0000-0000-0000-000000000001",
        )

    async def get_reminder(self, reminder_id: str) -> ReminderDTO:
        return ReminderDTO(
            reminder_id=reminder_id,
            text="九点打卡",
            remind_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            status="pending",
            conversation_id="conversation-1",
            session_id="session-1",
            workflow_id=f"reminder:{reminder_id}",
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

    async def cancel_reminder(self, command: CancelReminderCommand) -> ReminderDTO:
        self.cancel_commands.append(command.reminder_id)
        return ReminderDTO(
            reminder_id=command.reminder_id,
            text="九点打卡",
            remind_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            status="canceled",
            conversation_id="conversation-1",
            session_id="session-1",
            workflow_id=f"reminder:{command.reminder_id}",
        )

    async def cancel_matching_reminder(
        self,
        *,
        conversation_id: str,
        session_id: str,
        text_hint: str,
    ) -> ReminderDTO:
        self.canceled_latest_calls.append((conversation_id, session_id))
        return ReminderDTO(
            reminder_id="00000000-0000-0000-0000-000000000031",
            text=text_hint,
            remind_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            status="canceled",
            conversation_id=conversation_id,
            session_id=session_id,
            workflow_id="reminder:r-31",
        )

    async def list_reminders(self, query: ListRemindersQuery) -> ReminderListDTO:
        self.list_queries.append(query)
        if query.status == "failed":
            return ReminderListDTO(
                items=[
                    ReminderDTO(
                        reminder_id="00000000-0000-0000-0000-000000000099",
                        text="失败提醒",
                        remind_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
                        timezone="Asia/Shanghai",
                        status="failed",
                        failure_stage="workflow_start",
                        failure_reason_code="RuntimeError",
                        retryable=True,
                        conversation_id="conversation-1",
                        session_id="session-1",
                        workflow_id=None,
                    )
                ]
            )
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

    async def reschedule_reminder(self, command: Any) -> ReminderDTO:
        self.reschedule_commands.append(
            (command.reminder_id, command.remind_at, command.timezone)
        )
        return ReminderDTO(
            reminder_id=command.reminder_id,
            text="九点打卡",
            remind_at=command.remind_at,
            timezone=command.timezone,
            status="pending",
            conversation_id="conversation-1",
            session_id="session-1",
            workflow_id=f"reminder:{command.reminder_id}",
        )

    async def link_task(
        self,
        *,
        reminder_id: str,
        task_id: str,
    ) -> ReminderDTO:
        self.linked_tasks.append((reminder_id, task_id))
        return ReminderDTO(
            reminder_id=reminder_id,
            text="九点打卡",
            remind_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            status="pending",
            linked_task_id=task_id,
            conversation_id="conversation-1",
            session_id="session-1",
            workflow_id=f"reminder:{reminder_id}",
        )

    async def retry_failed_reminder(self, command: Any) -> ReminderDTO:
        self.retry_commands.append(command.reminder_id)
        return ReminderDTO(
            reminder_id=command.reminder_id,
            text="失败提醒",
            remind_at=datetime(2026, 3, 23, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            status="pending",
            conversation_id="conversation-1",
            session_id="session-1",
            workflow_id=f"reminder:{command.reminder_id}",
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
                    memory_type="note",
                    conversation_id=query.conversation_id,
                    session_id=query.session_id,
                    archived_at=None,
                )
            ],
            recent_activity=[
                AuditEventDTO(
                    kind="message",
                    event_id="evt-1",
                    recorded_at="2026-03-22T10:00:00+00:00",
                    conversation_id=query.conversation_id,
                    session_id=query.session_id,
                    trace_id=None,
                    chain_id=None,
                    request_id=None,
                    success=True,
                    summary="inbound:feishu:text",
                    payload={"text": "你好"},
                )
            ],
        )

    async def get_today_view(self, query: GetOverviewQuery) -> OverviewDTO:
        return await self.get_overview(query)

    async def get_working_set_view(self, query: GetOverviewQuery) -> OverviewDTO:
        return await self.get_overview(query)


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
async def test_intent_classifier_supports_greeting_by_rule() -> None:
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
            text="hey",
            raw_payload={"text": "hey"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.GREETING
    assert result.source == "rules"


@pytest.mark.asyncio
async def test_intent_classifier_supports_help_by_rule() -> None:
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
            text="你可以帮我做什么",
            raw_payload={"text": "你可以帮我做什么"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.HELP_SHOW
    assert result.source == "rules"


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
    llm_gateway = FakeLLMGateway('{"intent":"task_create","content":"整理会议纪要"}')
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=llm_gateway,
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
    assert len(overview_service.queries) == 1
    assert llm_gateway.last_request is not None
    assert "当前会话上下文：" in llm_gateway.last_request.prompt


@pytest.mark.asyncio
async def test_intent_handler_replies_to_greeting() -> None:
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FailingLLMGateway(),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=FakeTaskService(),
        memory_service=FakeMemoryService(),
        reminder_service=FakeReminderService(),
        overview_service=FakeOverviewService(),
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
            text="hey",
            raw_payload={"text": "hey"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled is True
    assert result.handled_by == "conversation"
    assert result.reason == "greeting_replied_via_rules"
    assert "你可以让我记提醒" in (result.response_text or "")


@pytest.mark.asyncio
async def test_intent_handler_shows_help() -> None:
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FailingLLMGateway(),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=FakeTaskService(),
        memory_service=FakeMemoryService(),
        reminder_service=FakeReminderService(),
        overview_service=FakeOverviewService(),
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
            text="你可以帮我做什么",
            raw_payload={"text": "你可以帮我做什么"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled is True
    assert result.handled_by == "conversation"
    assert result.reason == "help_shown_via_rules"
    assert "提醒" in (result.response_text or "")
    assert "待办" in (result.response_text or "")


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
    assert result.reason == "task_listed_via_rules"
    assert "你现在还有 1 个待办" in (result.response_text or "")
    assert task_service.list_queries


@pytest.mark.asyncio
async def test_intent_classifier_supports_task_search_by_rule() -> None:
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
            text="搜索任务 纪要",
            raw_payload={"text": "搜索任务 纪要"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.TASK_LIST
    assert result.content == "纪要"
    assert result.status is None


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_task_search_result() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"task_list","content":"纪要"}'),
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
            text="搜索任务 纪要",
            raw_payload={"text": "搜索任务 纪要"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "task"
    assert task_service.list_queries[-1].query == "纪要"
    assert "匹配“纪要”的任务" in (result.response_text or "")


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_completed_task_list_by_rule() -> None:
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
            text="查看已完成任务",
            raw_payload={"text": "查看已完成任务"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.TASK_LIST
    assert result.status == "completed"


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
    assert result.reason == "task_completed_via_rules"
    assert task_service.completed_latest_calls == [("conversation-1", "session-1")]
    assert "已经帮你完成这个待办了" in (result.response_text or "")
    assert "最近待办" in (result.response_text or "")


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_complete_matching_task() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"task_complete","content":"纪要"}'),
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
            text="完成任务 纪要",
            raw_payload={"text": "完成任务 纪要"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "task"
    assert result.reason == "task_completed_via_rules"
    assert "已经帮你完成这个待办了" in (result.response_text or "")
    assert "纪要" in (result.response_text or "")


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
    assert result.reason == "task_canceled_via_rules"
    assert task_service.canceled_latest_calls == [("conversation-1", "session-1")]
    assert "这个待办我已经取消了" in (result.response_text or "")
    assert "最近待办" in (result.response_text or "")


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
    assert result.reason == "memory_archived_via_rules"
    assert memory_service.archived_latest_calls == [("conversation-1", "session-1")]
    assert "这条记忆我已经归档了" in (result.response_text or "")
    assert "最近记忆" in (result.response_text or "")


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_archive_matching_memory() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"memory_archive","content":"九点提醒"}'),
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
            text="归档记忆 九点提醒",
            raw_payload={"text": "归档记忆 九点提醒"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "memory"
    assert result.reason == "memory_archived_via_rules"
    assert "这条记忆我已经归档了" in (result.response_text or "")
    assert "九点提醒" in (result.response_text or "")


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
    assert result.reason == "memory_listed_via_rules"
    assert "当前活跃记忆有 1 个" in (result.response_text or "")
    assert memory_service.list_queries


@pytest.mark.asyncio
async def test_intent_classifier_supports_memory_search_by_rule() -> None:
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
            text="搜索记忆 九点提醒",
            raw_payload={"text": "搜索记忆 九点提醒"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.MEMORY_LIST
    assert result.content == "九点提醒"
    assert result.status == "active"


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_archived_memory_list_by_rule() -> None:
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
            text="查看已归档记忆",
            raw_payload={"text": "查看已归档记忆"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.MEMORY_LIST
    assert result.status == "archived"


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
    assert result.reason == "reminder_canceled_via_rules"
    assert reminder_service.canceled_latest_calls == [("conversation-1", "session-1")]
    assert "这条提醒我已经取消了" in (result.response_text or "")
    assert "最近提醒" in (result.response_text or "")


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_cancel_matching_reminder() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"reminder_cancel","content":"打卡"}'),
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
            text="取消提醒 打卡",
            raw_payload={"text": "取消提醒 打卡"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "reminder"
    assert result.reason == "reminder_canceled_via_rules"
    assert "这条提醒我已经取消了" in (result.response_text or "")
    assert "打卡" in (result.response_text or "")


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
    assert "你现在有 1 个提醒" in (result.response_text or "")
    assert reminder_service.list_queries


@pytest.mark.asyncio
async def test_intent_classifier_supports_reminder_search_by_rule() -> None:
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
            text="搜索提醒 打卡",
            raw_payload={"text": "搜索提醒 打卡"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.REMINDER_LIST
    assert result.content == "打卡"
    assert result.status is None


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_reminder_search_result() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"reminder_list","content":"打卡"}'),
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
            text="搜索提醒 打卡",
            raw_payload={"text": "搜索提醒 打卡"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "reminder"
    assert reminder_service.list_queries[-1].query == "打卡"
    assert "匹配“打卡”的提醒" in (result.response_text or "")


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_canceled_reminder_list_by_rule() -> None:
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
            text="查看已取消提醒",
            raw_payload={"text": "查看已取消提醒"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.REMINDER_LIST
    assert result.status == "canceled"


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_failed_reminder_list_by_rule() -> None:
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
            text="查看失败提醒",
            raw_payload={"text": "查看失败提醒"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result.intent == ConversationIntent.REMINDER_LIST
    assert result.status == "failed"


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
    assert result.reason == "overview_shown_via_rules"
    assert "我先帮你看了一眼当前会话" in (result.response_text or "")
    assert overview_service.queries[0].conversation_id == "conversation-1"


@pytest.mark.asyncio
async def test_intent_handler_dispatches_to_recent_activity_view() -> None:
    task_service = FakeTaskService()
    memory_service = FakeMemoryService()
    reminder_service = FakeReminderService()
    overview_service = FakeOverviewService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"activity_show","content":null}'),
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
            text="查看最近活动",
            raw_payload={"text": "查看最近活动"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "overview"
    assert result.reason == "activity_shown_via_rules"
    assert "最近这几步我帮你处理的是" in (result.response_text or "")
    query = overview_service.queries[-1]
    assert query.reminder_limit == 0
    assert query.task_limit == 0
    assert query.memory_limit == 0


@pytest.mark.asyncio
async def test_intent_handler_returns_feedback_when_latest_task_missing() -> None:
    task_service = FakeTaskService()
    task_service.complete_latest_error = TaskNotFoundError("当前会话没有可完成的待办任务。")
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
    assert result.reason == "task_complete_feedback"
    assert result.response_text == "当前会话没有可完成的待办任务。"


@pytest.mark.asyncio
async def test_intent_handler_converts_task_to_reminder() -> None:
    task_service = FakeTaskService()
    reminder_service = FakeReminderService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway(
                '{"intent":"task_to_reminder","content":null,"remind_at":"2026-03-23T09:00:00+08:00","timezone":"Asia/Shanghai"}'
            ),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=FakeMemoryService(),
        reminder_service=reminder_service,
        overview_service=FakeOverviewService(),
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
            text="这个待办明天早上提醒我",
            raw_payload={"text": "这个待办明天早上提醒我"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "reminder"
    assert result.reason == "task_converted_to_reminder_via_llm"
    assert task_service.attached_reminders == [
        ("t-1", "00000000-0000-0000-0000-000000000001")
    ]
    assert "把这条待办挂上提醒" in (result.response_text or "")


@pytest.mark.asyncio
async def test_intent_handler_converts_reminder_to_task() -> None:
    task_service = FakeTaskService()
    reminder_service = FakeReminderService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway('{"intent":"reminder_to_task","content":null}'),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=task_service,
        memory_service=FakeMemoryService(),
        reminder_service=reminder_service,
        overview_service=FakeOverviewService(),
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
            text="改成待办",
            raw_payload={"text": "改成待办"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "task"
    assert result.reason == "reminder_converted_to_task_via_llm"
    assert reminder_service.linked_tasks == [("r-1", "00000000-0000-0000-0000-000000000001")]
    assert "改成待办" in (result.response_text or "")


@pytest.mark.asyncio
async def test_intent_handler_retries_failed_reminder() -> None:
    reminder_service = FakeReminderService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FailingLLMGateway(),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=FakeTaskService(),
        memory_service=FakeMemoryService(),
        reminder_service=reminder_service,
        overview_service=FakeOverviewService(),
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
            text="重试失败提醒",
            raw_payload={"text": "重试失败提醒"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "reminder"
    assert result.reason == "reminder_retried_via_rules"
    assert reminder_service.retry_commands == ["00000000-0000-0000-0000-000000000099"]
    assert "重新尝试启动" in (result.response_text or "")


@pytest.mark.asyncio
async def test_intent_handler_reschedules_reminder() -> None:
    reminder_service = FakeReminderService()
    handler = IntentConversationHandler(
        classifier=LLMFirstConversationIntentClassifier(
            llm_gateway=FakeLLMGateway(
                '{"intent":"reminder_reschedule","content":null,"remind_at":"2026-03-24T09:00:00+08:00","timezone":"Asia/Shanghai"}'
            ),
            model="gpt-test",
            api_key_suffix="90abcdef",
        ),
        task_service=FakeTaskService(),
        memory_service=FakeMemoryService(),
        reminder_service=reminder_service,
        overview_service=FakeOverviewService(),
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
            text="把这个提醒改到明天九点",
            raw_payload={"text": "把这个提醒改到明天九点"},
        ),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled_by == "reminder"
    assert result.reason == "reminder_rescheduled_via_llm"
    assert reminder_service.reschedule_commands
    assert "改时间" in (result.response_text or "")
