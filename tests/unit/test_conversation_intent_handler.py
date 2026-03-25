import inspect

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.intent_handler import (
    IntentConversationHandler,
    LegacyIntentConversationHandler,
)
from app.application.conversations.kernel.facade import (
    ConversationKernelFacade,
    ConversationKernelOutcome,
)
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.results import AssistantExecutionResult
from app.application.conversations.kernel.state import AssistantTurnContext


class FakeKernelFacade(ConversationKernelFacade):
    def __init__(self, outcome: ConversationKernelOutcome | None) -> None:
        self.turn_context_builder = object()
        self.planner = object()
        self.executor = object()
        self.renderer = object()
        self.outcome = outcome
        self.calls: list[tuple[str, str, str | None]] = []

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationKernelOutcome:
        self.calls.append((conversation_id, session_id, command.text))
        assert self.outcome is not None
        return self.outcome


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


def _build_outcome() -> ConversationKernelOutcome:
    return ConversationKernelOutcome(
        turn_context=AssistantTurnContext(
            conversation_id="conversation-1",
            session_id="session-1",
            latest_user_text="完成第三个",
        ),
        plan=AssistantActionPlan(
            intent="task_complete",
            action="complete_task",
            object_type="task",
            object_id="task-3",
            confidence=0.94,
            reasoning="rules",
        ),
        execution_result=AssistantExecutionResult(
            success=True,
            action="complete_task",
            object_type="task",
            object_id="task-3",
            object_title="第三个任务",
        ),
        response_text="好的，第三个任务已完成。",
        handled_by="task",
        reason="task_completed_via_rules",
        assistant_turn_state={"dialogue_mode": "normal"},
    )


def test_intent_handler_only_depends_on_kernel_facade() -> None:
    parameters = inspect.signature(LegacyIntentConversationHandler.__init__).parameters

    assert list(parameters) == ["self", "kernel_facade"]


def test_intent_handler_is_kept_as_legacy_alias() -> None:
    assert IntentConversationHandler is LegacyIntentConversationHandler


@pytest.mark.asyncio
async def test_intent_handler_delegates_to_legacy_kernel_facade() -> None:
    facade = FakeKernelFacade(_build_outcome())
    handler = LegacyIntentConversationHandler(kernel_facade=facade)

    result = await handler.handle(
        _build_command("完成第三个"),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is not None
    assert result.handled is True
    assert result.handled_by == "task"
    assert facade.calls == [("conversation-1", "session-1", "完成第三个")]


@pytest.mark.asyncio
async def test_intent_handler_returns_none_when_legacy_kernel_cannot_handle() -> None:
    facade = FakeKernelFacade(
        ConversationKernelOutcome(
            turn_context=AssistantTurnContext(
                conversation_id="conversation-1",
                session_id="session-1",
                latest_user_text="闲聊",
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
    )
    handler = LegacyIntentConversationHandler(kernel_facade=facade)

    result = await handler.handle(
        _build_command("闲聊"),
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert result is None
