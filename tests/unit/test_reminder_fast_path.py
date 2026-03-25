import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.reminders.conversation_handler import ReminderConversationHandler
from app.application.reminders.dto import ReminderInboundMessageResult


class FakeReminderService:
    def __init__(self, result: ReminderInboundMessageResult) -> None:
        self.result = result

    async def handle_inbound_message(self, command: object) -> ReminderInboundMessageResult:
        _ = command
        return self.result


def _build_command(text: str) -> HandleInboundConversationMessageCommand:
    return HandleInboundConversationMessageCommand(
        channel="feishu",
        message_type="text",
        user_identity="user-1",
        external_message_id="om-1",
        root_message_id=None,
        parent_message_id=None,
        chat_id="oc-1",
        thread_id="ot-1",
        text=text,
        raw_payload={"text": text},
    )


@pytest.mark.asyncio
async def test_收到_走_completed_fast_path() -> None:
    handler = ReminderConversationHandler(
        FakeReminderService(
            ReminderInboundMessageResult(
                handled=True,
                reminder_id="r-1",
                reason="reminder_replied",
                response_text="好的，这条提醒我帮你记为已收到。",
                decision="completed",
                match_source="exact_message_relation",
            )
        )
    )

    result = await handler.handle(_build_command("收到"), conversation_id="c-1", session_id="s-1")

    assert result.decision == "completed"
    assert result.assistant_turn_state is not None


@pytest.mark.asyncio
async def test_同一聊天里的普通闲聊消息_走_pass_to_kernel() -> None:
    handler = ReminderConversationHandler(
        FakeReminderService(
            ReminderInboundMessageResult(
                handled=False,
                reason="not_reminder_reply",
                decision="pass_to_kernel",
            )
        )
    )

    result = await handler.handle(
        _build_command("今天天气不错"), conversation_id="c-1", session_id="s-1"
    )

    assert result.decision == "pass_to_kernel"
    assert result.handled_by is None


@pytest.mark.asyncio
async def test_最近_pending_提醒只进入_needs_confirmation() -> None:
    handler = ReminderConversationHandler(
        FakeReminderService(
            ReminderInboundMessageResult(
                handled=False,
                reminder_id="r-2",
                reason="reminder_match_low_confidence",
                response_text="我理解成你可能是在回复最近这条提醒，但这一步我不自动完成。",
                decision="needs_confirmation",
                match_source="same_chat_recent_dispatch",
            )
        )
    )

    result = await handler.handle(_build_command("收到"), conversation_id="c-1", session_id="s-1")

    assert result.decision == "needs_confirmation"
    assert result.assistant_turn_state is not None
    assert result.assistant_turn_state["dialogue_mode"] == "normal"
    assert result.assistant_turn_state["focused_object"]["object_type"] == "reminder"
