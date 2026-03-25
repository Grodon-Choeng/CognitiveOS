import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationFastPathResult
from app.application.conversations.kernel.facade import (
    ConversationKernelFacade,
    ConversationKernelOutcome,
)
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.results import (
    AssistantConfirmationResult,
    AssistantExecutionResult,
)
from app.application.conversations.kernel.state import AssistantTurnContext
from app.application.conversations.ports import (
    ConversationContextResolver,
    ResolvedConversationContext,
)
from app.application.conversations.service import ConversationApplicationService
from app.infrastructure.types import JSONObject
from app.observability.message_events import MessageEventRecord


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


class FakeMessageEventRecorder:
    def __init__(self) -> None:
        self.records: list[MessageEventRecord] = []

    async def record(self, record: MessageEventRecord) -> None:
        self.records.append(record)


class FakeReminderHandler:
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


class FakeTurnStateStore:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str, JSONObject]] = []

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
        self.saved.append((conversation_id, session_id, state))


class FakeKernelFacade(ConversationKernelFacade):
    def __init__(self, outcome: ConversationKernelOutcome) -> None:
        self.turn_context_builder = object()
        self.planner = object()
        self.executor = object()
        self.renderer = object()
        self.outcome = outcome

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationKernelOutcome:
        _ = (command, conversation_id, session_id)
        return self.outcome

    @staticmethod
    def build_debug_payload(outcome: ConversationKernelOutcome) -> JSONObject:
        return {
            "stage": "kernel",
            "plan_action": outcome.plan.action,
            "response_text": outcome.response_text,
        }


def _build_command(text: str) -> HandleInboundConversationMessageCommand:
    return HandleInboundConversationMessageCommand(
        channel="web",
        message_type="text",
        user_identity="user-1",
        external_message_id=None,
        root_message_id=None,
        parent_message_id=None,
        chat_id=None,
        thread_id=None,
        text=text,
        raw_payload={"text": text},
    )


def _build_kernel_outcome(
    *,
    execution_result: AssistantExecutionResult | AssistantConfirmationResult | None,
    response_text: str | None,
    assistant_turn_state: JSONObject | None,
    reason: str,
    handled_by: str = "task",
) -> ConversationKernelOutcome:
    return ConversationKernelOutcome(
        turn_context=AssistantTurnContext(
            conversation_id="conversation-test",
            session_id="session-test",
            latest_user_text="用户输入",
        ),
        plan=AssistantActionPlan(
            intent="task_complete",
            action="complete_task",
            object_type="task",
            object_id="task-1" if execution_result is not None else None,
            confidence=0.92,
            reasoning="rules",
        ),
        execution_result=execution_result,
        response_text=response_text,
        handled_by=handled_by,
        reason=reason,
        assistant_turn_state=assistant_turn_state,
    )


def _build_service(
    *,
    reminder_result: ConversationFastPathResult,
    kernel_outcome: ConversationKernelOutcome,
    turn_state_store: FakeTurnStateStore | None = None,
) -> ConversationApplicationService:
    return ConversationApplicationService(
        conversation_context_resolver=FakeConversationContextResolver(),
        message_event_recorder=FakeMessageEventRecorder(),
        reminder_handler=FakeReminderHandler(reminder_result),
        kernel_facade=FakeKernelFacade(kernel_outcome),
        turn_state_store=turn_state_store or FakeTurnStateStore(),
    )


@pytest.mark.asyncio
async def test_conversation_service_records_completed_reminder_fast_path_state() -> None:
    turn_state_store = FakeTurnStateStore()
    service = _build_service(
        reminder_result=ConversationFastPathResult(
            decision="completed",
            conversation_id="conversation-test",
            session_id="session-test",
            handled_by="reminder",
            reason="reminder_replied",
            response_text="好的，这条提醒我帮你记为已收到。",
            assistant_turn_state={
                "dialogue_mode": "normal",
                "last_assistant_action": {"action_type": "reply_reminder", "success": True},
            },
            debug={"stage": "reminder_fast_path", "decision": "completed"},
        ),
        kernel_outcome=_build_kernel_outcome(
            execution_result=None,
            response_text=None,
            assistant_turn_state=None,
            reason="unused",
        ),
        turn_state_store=turn_state_store,
    )

    result = await service.handle_inbound_message(_build_command("收到"))

    assert result.handled is True
    assert result.handled_by == "reminder"
    assert turn_state_store.saved[0][2]["last_assistant_action"]["action_type"] == "reply_reminder"


@pytest.mark.asyncio
async def test_conversation_service_returns_fast_path_confirmation_without_entering_kernel() -> (
    None
):
    service = _build_service(
        reminder_result=ConversationFastPathResult(
            decision="needs_confirmation",
            conversation_id="conversation-test",
            session_id="session-test",
            handled_by="reminder",
            reason="reminder_needs_confirmation",
            response_text="我理解成你在回复最近这条提醒，先帮你确认一下。",
            assistant_turn_state={
                "dialogue_mode": "confirmation",
                "last_assistant_action": {
                    "action_type": "reply_reminder_needs_confirmation",
                    "success": True,
                },
            },
            debug={"stage": "reminder_fast_path", "decision": "needs_confirmation"},
        ),
        kernel_outcome=_build_kernel_outcome(
            execution_result=None,
            response_text=None,
            assistant_turn_state=None,
            reason="unused",
        ),
    )

    result = await service.handle_inbound_message(_build_command("收到"))

    assert result.handled is True
    assert result.reason == "reminder_needs_confirmation"
    assert "先帮你确认一下" in (result.response_text or "")


@pytest.mark.asyncio
async def test_conversation_service_runs_kernel_when_fast_path_passes() -> None:
    turn_state_store = FakeTurnStateStore()
    service = _build_service(
        reminder_result=ConversationFastPathResult(
            decision="pass_to_kernel",
            conversation_id="conversation-test",
            session_id="session-test",
        ),
        kernel_outcome=_build_kernel_outcome(
            execution_result=AssistantExecutionResult(
                success=True,
                action="complete_task",
                object_type="task",
                object_id="task-1",
                object_title="整理纪要",
            ),
            response_text="好的，已完成整理纪要。",
            assistant_turn_state={
                "dialogue_mode": "normal",
                "focused_object": {"object_type": "task", "object_id": "task-1"},
            },
            reason="task_completed_via_rules",
        ),
        turn_state_store=turn_state_store,
    )

    result = await service.handle_inbound_message(_build_command("完成这个"))

    assert result.handled is True
    assert result.handled_by == "task"
    assert turn_state_store.saved[0][2]["focused_object"]["object_id"] == "task-1"


@pytest.mark.asyncio
async def test_conversation_service_includes_kernel_debug_payload() -> None:
    service = _build_service(
        reminder_result=ConversationFastPathResult(
            decision="pass_to_kernel",
            conversation_id="conversation-test",
            session_id="session-test",
        ),
        kernel_outcome=_build_kernel_outcome(
            execution_result=AssistantConfirmationResult(
                prompt="我理解成你要操作这条记录，先帮你确认一下。",
                confirm_action="cancel_reminder",
                preview_text="买药提醒",
            ),
            response_text="我理解成你要操作这条记录，先帮你确认一下。",
            assistant_turn_state={
                "dialogue_mode": "confirmation",
            },
            reason="cancel_reminder_needs_confirmation",
            handled_by="reminder",
        ),
    )

    result = await service.handle_inbound_message(
        _build_command("取消最后一个提醒"), include_debug=True
    )

    assert result.debug == {
        "stage": "kernel",
        "plan_action": "complete_task",
        "response_text": "我理解成你要操作这条记录，先帮你确认一下。",
    }
