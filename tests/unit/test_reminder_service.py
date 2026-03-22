from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType

import pytest

from app.application.conversations.ports import (
    ConversationContextResolver,
    ResolvedConversationContext,
)
from app.application.reminders.commands import (
    CancelReminderCommand,
    CreateReminderCommand,
    HandleReminderInboundMessageCommand,
    HandleReminderReplyCommand,
)
from app.application.reminders.errors import (
    ReminderNotFoundError,
    ReminderStateConflictError,
    ReminderWorkflowCancelError,
    ReminderWorkflowStartError,
)
from app.application.reminders.ports import (
    ReminderDispatchTarget,
    ReminderUnitOfWork,
    ReminderWorkflowGateway,
)
from app.application.reminders.service import ReminderApplicationService
from app.domain.reminders.entities import Reminder, ReminderStatus
from app.domain.reminders.repository import ReminderRepository
from app.domain.reminders.value_objects import ReminderId


class FakeReminderRepository(ReminderRepository):
    def __init__(self) -> None:
        self.items: dict[str, Reminder] = {}

    async def add(self, reminder: Reminder) -> None:
        self.items[str(reminder.reminder_id.value)] = reminder

    async def get(self, reminder_id: ReminderId) -> Reminder | None:
        return self.items.get(str(reminder_id.value))

    async def get_by_dispatch_message_id(self, dispatch_message_id: str) -> Reminder | None:
        for reminder in self.items.values():
            if reminder.dispatch_message_id == dispatch_message_id:
                return reminder
        return None

    async def get_latest_pending_by_conversation(
        self,
        conversation_id: str,
    ) -> Reminder | None:
        for reminder in reversed(list(self.items.values())):
            if reminder.status.value == "pending" and reminder.conversation_id == conversation_id:
                return reminder
        return None

    async def get_latest_pending_by_dispatch_chat(
        self,
        channel: str,
        recipient_id: str,
        chat_id: str,
        thread_id: str | None = None,
    ) -> Reminder | None:
        for reminder in reversed(list(self.items.values())):
            if (
                reminder.status.value == "pending"
                and reminder.dispatch_channel == channel
                and reminder.dispatch_recipient_id == recipient_id
                and reminder.dispatch_chat_id == chat_id
                and reminder.dispatch_thread_id == thread_id
            ):
                return reminder
        return None

    async def get_latest_pending_by_dispatch(
        self,
        channel: str,
        recipient_id: str,
    ) -> Reminder | None:
        for reminder in reversed(list(self.items.values())):
            if (
                reminder.status.value == "pending"
                and reminder.dispatch_channel == channel
                and reminder.dispatch_recipient_id == recipient_id
            ):
                return reminder
        return None

    async def update(self, reminder: Reminder) -> None:
        self.items[str(reminder.reminder_id.value)] = reminder


class FakeReminderUnitOfWork(ReminderUnitOfWork):
    def __init__(self, repository: FakeReminderRepository) -> None:
        self.reminders: ReminderRepository = repository
        self.commit_count = 0

    async def __aenter__(self) -> "FakeReminderUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc, tb)

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        return None


@dataclass
class StartedWorkflow:
    reminder_id: str
    dispatch_target: ReminderDispatchTarget


class FakeReminderWorkflowGateway(ReminderWorkflowGateway):
    def __init__(self) -> None:
        self.started: list[StartedWorkflow] = []
        self.recorded_replies: list[tuple[str, str]] = []
        self.canceled_workflows: list[str] = []
        self.start_error: Exception | None = None
        self.cancel_error: Exception | None = None

    async def start_reminder(
        self,
        reminder: Reminder,
        dispatch_target: ReminderDispatchTarget,
    ) -> str:
        if self.start_error is not None:
            raise self.start_error
        reminder_id = str(reminder.reminder_id.value)
        self.started.append(
            StartedWorkflow(
                reminder_id=reminder_id,
                dispatch_target=dispatch_target,
            )
        )
        return f"reminder:{reminder_id}"

    async def record_user_reply(self, workflow_id: str, reply_text: str) -> None:
        self.recorded_replies.append((workflow_id, reply_text))

    async def cancel_reminder(self, workflow_id: str) -> None:
        if self.cancel_error is not None:
            raise self.cancel_error
        self.canceled_workflows.append(workflow_id)


class FakeConversationContextResolver(ConversationContextResolver):
    async def resolve_for_outbound(
        self,
        *,
        provided_conversation_id: str | None,
        provided_session_id: str | None,
        source_channel: str | None,
        source_user_id: str | None,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext:
        _ = (source_channel, source_user_id, source_chat_id, source_thread_id)
        return ResolvedConversationContext(
            conversation_id=provided_conversation_id or "conversation-test",
            session_id=provided_session_id or "session-test",
        )

    async def resolve_for_inbound(
        self,
        *,
        source_channel: str,
        source_user_id: str,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext:
        _ = (source_channel, source_user_id, source_chat_id, source_thread_id)
        return ResolvedConversationContext(
            conversation_id="conversation-test",
            session_id="session-test",
        )


def create_fake_unit_of_work_factory(
    repository: FakeReminderRepository,
) -> Callable[[], FakeReminderUnitOfWork]:
    def factory() -> FakeReminderUnitOfWork:
        return FakeReminderUnitOfWork(repository)

    return factory


@pytest.mark.asyncio
async def test_create_reminder_persists_and_starts_workflow() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    result = await service.create_reminder(
        CreateReminderCommand(
            text="明天上午九点提醒我打卡",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            dispatch_channel="console",
            dispatch_recipient_id="user-1",
        )
    )

    saved = repository.items[result.reminder_id]
    assert result.workflow_id == f"reminder:{result.reminder_id}"
    assert result.conversation_id == "conversation-test"
    assert result.session_id == "session-test"
    assert saved.workflow_id == result.workflow_id
    assert saved.conversation_id == "conversation-test"
    assert saved.session_id == "session-test"
    assert saved.dispatch_channel == "console"
    assert saved.dispatch_recipient_id == "user-1"
    assert workflow_gateway.started[0].dispatch_target.channel == "console"
    assert workflow_gateway.started[0].dispatch_target.recipient_id == "user-1"


@pytest.mark.asyncio
async def test_create_reminder_marks_failed_when_workflow_start_fails() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    workflow_gateway.start_error = RuntimeError("Temporal 不可用")
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    with pytest.raises(ReminderWorkflowStartError) as exc_info:
        await service.create_reminder(
            CreateReminderCommand(
                text="明天上午九点提醒我打卡",
                remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
                timezone="Asia/Shanghai",
                dispatch_channel="console",
                dispatch_recipient_id="user-1",
            )
        )

    saved = next(iter(repository.items.values()))
    assert "提醒工作流启动失败" in str(exc_info.value)
    assert saved.status.value == "failed"
    assert saved.workflow_id is None


@pytest.mark.asyncio
async def test_handle_reply_updates_reminder_and_signals_workflow() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    created = await service.create_reminder(
        CreateReminderCommand(
            text="提醒我提交日报",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )

    reply_result = await service.handle_reply(
        HandleReminderReplyCommand(
            reminder_id=created.reminder_id,
            reply_text="我已经提交了",
        )
    )

    saved = repository.items[created.reminder_id]
    assert reply_result.accepted is True
    assert reply_result.status == "completed"
    assert saved.last_user_reply == "我已经提交了"
    assert saved.status.value == "completed"
    assert workflow_gateway.recorded_replies == [(created.workflow_id or "", "我已经提交了")]


@pytest.mark.asyncio
async def test_handle_reply_rejects_non_pending_reminder() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    created = await service.create_reminder(
        CreateReminderCommand(
            text="提醒我提交日报",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )
    repository.items[created.reminder_id].status = ReminderStatus.COMPLETED

    with pytest.raises(ReminderStateConflictError):
        await service.handle_reply(
            HandleReminderReplyCommand(
                reminder_id=created.reminder_id,
                reply_text="我已经提交了",
            )
        )


@pytest.mark.asyncio
async def test_get_reminder_returns_existing_reminder() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    created = await service.create_reminder(
        CreateReminderCommand(
            text="提醒我提交日报",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )

    fetched = await service.get_reminder(created.reminder_id)

    assert fetched.reminder_id == created.reminder_id
    assert fetched.status == "pending"


@pytest.mark.asyncio
async def test_cancel_reminder_updates_status_and_cancels_workflow() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    created = await service.create_reminder(
        CreateReminderCommand(
            text="提醒我提交日报",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )

    canceled = await service.cancel_reminder(CancelReminderCommand(reminder_id=created.reminder_id))

    saved = repository.items[created.reminder_id]
    assert canceled.status == "canceled"
    assert saved.status.value == "canceled"
    assert workflow_gateway.canceled_workflows == [created.workflow_id or ""]


@pytest.mark.asyncio
async def test_cancel_reminder_is_idempotent_for_already_canceled_reminder() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    created = await service.create_reminder(
        CreateReminderCommand(
            text="提醒我提交日报",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )
    repository.items[created.reminder_id].status = ReminderStatus.CANCELED

    canceled = await service.cancel_reminder(CancelReminderCommand(reminder_id=created.reminder_id))

    assert canceled.status == "canceled"
    assert workflow_gateway.canceled_workflows == []


@pytest.mark.asyncio
async def test_cancel_reminder_rejects_non_pending_reminder() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    created = await service.create_reminder(
        CreateReminderCommand(
            text="提醒我提交日报",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )
    repository.items[created.reminder_id].status = ReminderStatus.COMPLETED

    with pytest.raises(ReminderStateConflictError):
        await service.cancel_reminder(CancelReminderCommand(reminder_id=created.reminder_id))


@pytest.mark.asyncio
async def test_cancel_reminder_raises_when_workflow_cancel_fails() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    workflow_gateway.cancel_error = RuntimeError("Temporal 不可用")
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    created = await service.create_reminder(
        CreateReminderCommand(
            text="提醒我提交日报",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )

    with pytest.raises(ReminderWorkflowCancelError):
        await service.cancel_reminder(CancelReminderCommand(reminder_id=created.reminder_id))

    assert repository.items[created.reminder_id].status.value == "pending"


@pytest.mark.asyncio
async def test_handle_reply_raises_when_reminder_not_found() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    with pytest.raises(ReminderNotFoundError):
        await service.handle_reply(
            HandleReminderReplyCommand(
                reminder_id="00000000-0000-0000-0000-000000000001",
                reply_text="收到",
            )
        )


@pytest.mark.asyncio
async def test_handle_inbound_message_matches_latest_pending_reminder() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    created = await service.create_reminder(
        CreateReminderCommand(
            text="提醒我喝水",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-test",
            dispatch_channel="feishu",
            dispatch_recipient_id="ou_123",
            dispatch_chat_id="oc_123",
            dispatch_thread_id="ot_123",
        )
    )

    result = await service.handle_inbound_message(
        HandleReminderInboundMessageCommand(
            conversation_id=None,
            session_id=None,
            channel="feishu",
            sender_id="ou_123",
            message_id="om_reply_1",
            root_message_id=None,
            parent_message_id=None,
            chat_id="oc_123",
            thread_id="ot_123",
            text="我已经喝了",
        )
    )

    saved = repository.items[created.reminder_id]
    assert result.handled is True
    assert result.reminder_id == created.reminder_id
    assert saved.last_user_reply == "我已经喝了"
    assert saved.status.value == "completed"
    assert workflow_gateway.recorded_replies == [(created.workflow_id or "", "我已经喝了")]


@pytest.mark.asyncio
async def test_handle_inbound_message_returns_not_handled_when_no_pending_reminder() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    result = await service.handle_inbound_message(
        HandleReminderInboundMessageCommand(
            conversation_id=None,
            session_id=None,
            channel="feishu",
            sender_id="ou_missing",
            message_id="om_reply_1",
            root_message_id=None,
            parent_message_id=None,
            chat_id="oc_123",
            thread_id="ot_123",
            text="我已经喝了",
        )
    )

    assert result.handled is False
    assert result.reason == "no_pending_reminder"


@pytest.mark.asyncio
async def test_handle_inbound_message_prefers_exact_dispatch_message_match() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    first = await service.create_reminder(
        CreateReminderCommand(
            text="第一个提醒",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-first",
            dispatch_channel="feishu",
            dispatch_recipient_id="ou_123",
            dispatch_chat_id="oc_123",
            dispatch_thread_id="ot_1",
        )
    )
    second = await service.create_reminder(
        CreateReminderCommand(
            text="第二个提醒",
            remind_at=datetime(2026, 3, 20, 9, 1, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-second",
            dispatch_channel="feishu",
            dispatch_recipient_id="ou_123",
            dispatch_chat_id="oc_123",
            dispatch_thread_id="ot_2",
        )
    )

    repository.items[first.reminder_id].dispatch_message_id = "om_parent_1"
    repository.items[second.reminder_id].dispatch_message_id = "om_parent_2"

    result = await service.handle_inbound_message(
        HandleReminderInboundMessageCommand(
            conversation_id=None,
            session_id=None,
            channel="feishu",
            sender_id="ou_123",
            message_id="om_reply_1",
            root_message_id=None,
            parent_message_id="om_parent_1",
            chat_id="oc_123",
            thread_id="ot_1",
            text="我回复的是第一个提醒",
        )
    )

    first_saved = repository.items[first.reminder_id]
    second_saved = repository.items[second.reminder_id]
    assert result.handled is True
    assert result.reminder_id == first.reminder_id
    assert first_saved.status.value == "completed"
    assert second_saved.status.value == "pending"


@pytest.mark.asyncio
async def test_handle_inbound_message_matches_same_chat_and_thread_before_fallback() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    first = await service.create_reminder(
        CreateReminderCommand(
            text="群聊线程 A 的提醒",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-thread-a",
            dispatch_channel="feishu",
            dispatch_recipient_id="ou_123",
            dispatch_chat_id="oc_group",
            dispatch_thread_id="ot_thread_a",
        )
    )
    second = await service.create_reminder(
        CreateReminderCommand(
            text="群聊线程 B 的提醒",
            remind_at=datetime(2026, 3, 20, 9, 1, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-thread-b",
            dispatch_channel="feishu",
            dispatch_recipient_id="ou_123",
            dispatch_chat_id="oc_group",
            dispatch_thread_id="ot_thread_b",
        )
    )

    result = await service.handle_inbound_message(
        HandleReminderInboundMessageCommand(
            conversation_id=None,
            session_id=None,
            channel="feishu",
            sender_id="ou_123",
            message_id="om_reply_thread_a",
            root_message_id=None,
            parent_message_id=None,
            chat_id="oc_group",
            thread_id="ot_thread_a",
            text="线程 A 回复",
        )
    )

    first_saved = repository.items[first.reminder_id]
    second_saved = repository.items[second.reminder_id]
    assert result.handled is True
    assert result.reminder_id == first.reminder_id
    assert first_saved.status.value == "completed"
    assert second_saved.status.value == "pending"


@pytest.mark.asyncio
async def test_handle_inbound_message_uses_conversation_before_chat_fallback() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    first = await service.create_reminder(
        CreateReminderCommand(
            text="飞书提醒",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-test",
            dispatch_channel="feishu",
            dispatch_recipient_id="ou_123",
            dispatch_chat_id="oc_feishu",
            dispatch_thread_id="ot_feishu",
        )
    )
    second = await service.create_reminder(
        CreateReminderCommand(
            text="同 chat 但不同 conversation",
            remind_at=datetime(2026, 3, 20, 9, 1, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-other",
            dispatch_channel="feishu",
            dispatch_recipient_id="ou_123",
            dispatch_chat_id="oc_feishu",
            dispatch_thread_id="ot_feishu",
        )
    )

    result = await service.handle_inbound_message(
        HandleReminderInboundMessageCommand(
            conversation_id=None,
            session_id=None,
            channel="feishu",
            sender_id="ou_123",
            message_id="om_reply_conversation",
            root_message_id=None,
            parent_message_id=None,
            chat_id="oc_feishu",
            thread_id="ot_feishu",
            text="conversation 优先匹配",
        )
    )

    first_saved = repository.items[first.reminder_id]
    second_saved = repository.items[second.reminder_id]
    assert result.handled is True
    assert result.reminder_id == first.reminder_id
    assert first_saved.status.value == "completed"
    assert second_saved.status.value == "pending"
