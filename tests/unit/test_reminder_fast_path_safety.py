from datetime import UTC, datetime

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationFastPathResult
from app.application.conversations.kernel.facade import (
    ConversationKernelFacade,
    ConversationKernelOutcome,
)
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.state import AssistantTurnContext
from app.application.conversations.ports import (
    ConversationContextResolver,
    ResolvedConversationContext,
)
from app.application.conversations.service import ConversationApplicationService
from app.application.reminders.commands import (
    CreateReminderCommand,
    HandleReminderInboundMessageCommand,
)
from app.application.reminders.service import ReminderApplicationService
from app.infrastructure.types import JSONObject
from app.observability.message_events import MessageEventRecord
from tests.unit.test_reminder_service import (
    FakeConversationContextResolver,
    FakeReminderRepository,
    FakeReminderWorkflowGateway,
    create_fake_unit_of_work_factory,
)


class RecordingKernelFacade(ConversationKernelFacade):
    def __init__(self) -> None:
        self.turn_context_builder = object()
        self.planner = object()
        self.executor = object()
        self.renderer = object()
        self.calls: list[str | None] = []

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationKernelOutcome:
        self.calls.append(command.text)
        return ConversationKernelOutcome(
            turn_context=AssistantTurnContext(
                conversation_id=conversation_id,
                session_id=session_id,
                latest_user_text=command.text,
            ),
            plan=AssistantActionPlan(
                intent="unknown",
                action=None,
                object_type=None,
                object_id=None,
                status="unsupported",
                reasoning="rules",
            ),
            execution_result=None,
            response_text=None,
            handled_by=None,
            reason=None,
            assistant_turn_state=None,
        )


class FakeMessageEventRecorder:
    async def record(self, record: MessageEventRecord) -> None:
        _ = record


class FakeTurnStateStore:
    async def load(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> JSONObject | None:
        _ = (conversation_id, session_id)
        return None

    async def save(
        self,
        *,
        conversation_id: str,
        session_id: str,
        state: JSONObject,
    ) -> None:
        _ = (conversation_id, session_id, state)


def _build_service() -> tuple[
    ReminderApplicationService,
    FakeReminderRepository,
    FakeReminderWorkflowGateway,
]:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    return service, repository, workflow_gateway


async def _create_feishu_reminder(
    service: ReminderApplicationService,
    *,
    text: str = "提醒我买药",
    conversation_id: str = "conversation-test",
    thread_id: str = "ot-1",
) -> str:
    created = await service.create_reminder(
        CreateReminderCommand(
            text=text,
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id=conversation_id,
            session_id="session-test",
            dispatch_channel="feishu",
            dispatch_recipient_id="ou_123",
            dispatch_chat_id="oc_123",
            dispatch_thread_id=thread_id,
        )
    )
    return created.reminder_id


def _build_inbound_command(text: str) -> HandleReminderInboundMessageCommand:
    return HandleReminderInboundMessageCommand(
        conversation_id=None,
        session_id=None,
        channel="feishu",
        sender_id="ou_123",
        message_id="om_reply_1",
        root_message_id=None,
        parent_message_id=None,
        chat_id="oc_123",
        thread_id="ot-1",
        text=text,
    )


@pytest.mark.asyncio
async def test_收到_高置信提醒回复可以直接_completed() -> None:
    service, repository, workflow_gateway = _build_service()
    reminder_id = await _create_feishu_reminder(service)
    repository.items[reminder_id].dispatch_message_id = "om_parent_1"

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
            thread_id="ot-1",
            text="收到",
        )
    )

    assert result.decision == "completed"
    assert repository.items[reminder_id].status.value == "completed"
    assert workflow_gateway.recorded_replies


@pytest.mark.asyncio
async def test_改成明天_不会把提醒直接标记_completed() -> None:
    service, repository, workflow_gateway = _build_service()
    reminder_id = await _create_feishu_reminder(service)
    repository.items[reminder_id].dispatch_message_id = "om_parent_1"

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
            thread_id="ot-1",
            text="改成明天",
        )
    )

    assert result.decision == "needs_confirmation"
    assert repository.items[reminder_id].status.value == "pending"
    assert workflow_gateway.recorded_replies == []


@pytest.mark.asyncio
async def test_不是这个_不会把提醒直接标记_completed() -> None:
    service, repository, workflow_gateway = _build_service()
    reminder_id = await _create_feishu_reminder(service)
    repository.items[reminder_id].dispatch_message_id = "om_parent_1"

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
            thread_id="ot-1",
            text="不是这个",
        )
    )

    assert result.decision == "pass_to_kernel"
    assert repository.items[reminder_id].status.value == "pending"
    assert workflow_gateway.recorded_replies == []


@pytest.mark.asyncio
async def test_同一聊天里的普通消息不会误命中最近_reminder() -> None:
    service, repository, workflow_gateway = _build_service()
    reminder_id = await _create_feishu_reminder(service)

    result = await service.handle_inbound_message(_build_inbound_command("今天天气不错"))

    assert result.decision == "pass_to_kernel"
    assert result.reason == "not_reminder_reply"
    assert repository.items[reminder_id].status.value == "pending"
    assert workflow_gateway.recorded_replies == []


@pytest.mark.asyncio
async def test_普通闲聊即使有高置信关联也仍然_pass_to_kernel() -> None:
    service, repository, workflow_gateway = _build_service()
    reminder_id = await _create_feishu_reminder(service)
    repository.items[reminder_id].dispatch_message_id = "om_parent_1"

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
            thread_id="ot-1",
            text="今天天气不错",
        )
    )

    assert result.decision == "pass_to_kernel"
    assert result.reason == "not_reminder_reply"
    assert repository.items[reminder_id].status.value == "pending"
    assert workflow_gateway.recorded_replies == []


@pytest.mark.asyncio
async def test_低置信收到_进入_needs_confirmation_而不是自动完成() -> None:
    service, repository, workflow_gateway = _build_service()
    reminder_id = await _create_feishu_reminder(service)

    result = await service.handle_inbound_message(_build_inbound_command("收到"))

    assert result.decision == "needs_confirmation"
    assert result.match_source == "same_conversation_pending"
    assert repository.items[reminder_id].status.value == "pending"
    assert workflow_gateway.recorded_replies == []


@pytest.mark.asyncio
async def test_这个提醒已经提醒过了呀_低置信时回到_kernel做真实对象解析() -> None:
    service, repository, workflow_gateway = _build_service()
    reminder_id = await _create_feishu_reminder(service)

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
            thread_id="ot-1",
            text="这个提醒已经提醒过了呀",
        )
    )

    assert result.decision == "pass_to_kernel"
    assert result.reason == "reminder_followup_acknowledgement_needs_kernel_resolution"
    assert repository.items[reminder_id].status.value == "pending"
    assert workflow_gateway.recorded_replies == []


class FakeConversationContextResolverForFastPath(ConversationContextResolver):
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
        _ = (
            provided_conversation_id,
            provided_session_id,
            source_channel,
            source_user_id,
            source_chat_id,
            source_thread_id,
        )
        return ResolvedConversationContext(
            conversation_id="conversation-test",
            session_id="session-test",
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


class StubReminderHandler:
    def __init__(self, result: ConversationFastPathResult) -> None:
        self.result = result

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationFastPathResult:
        _ = (command, conversation_id, session_id)
        return self.result


@pytest.mark.asyncio
async def test_fast_path_低置信时会回到_kernel主流程() -> None:
    kernel_facade = RecordingKernelFacade()
    service = ConversationApplicationService(
        conversation_context_resolver=FakeConversationContextResolverForFastPath(),
        message_event_recorder=FakeMessageEventRecorder(),
        reminder_handler=StubReminderHandler(
            ConversationFastPathResult(
                decision="pass_to_kernel",
                conversation_id="conversation-test",
                session_id="session-test",
                handled_by=None,
                reason="reminder_match_low_confidence",
                response_text=None,
            )
        ),
        kernel_facade=kernel_facade,
        react_kernel=kernel_facade,
        conversation_use_react_agent=False,
        turn_state_store=FakeTurnStateStore(),
    )

    result = await service.handle_inbound_message(
        HandleInboundConversationMessageCommand(
            channel="feishu",
            message_type="text",
            user_identity="ou_123",
            external_message_id="om-1",
            root_message_id=None,
            parent_message_id=None,
            chat_id="oc_123",
            thread_id="ot-1",
            text="收到",
            raw_payload={"text": "收到"},
        )
    )

    assert result.reason == "no_handler_accepted"
    assert kernel_facade.calls == ["收到"]
