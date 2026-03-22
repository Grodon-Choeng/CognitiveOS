from dataclasses import dataclass

import pytest

from app.application.conversations.dto import ConversationInboundResult
from app.bootstrap.inbound_events import ConversationInboundEventRecorder
from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    OutboundMessage,
    SendResult,
)
from app.infrastructure.integrations.messaging.feishu_webhook import InboundMessageEvent


@dataclass
class FakeConversationService:
    result: ConversationInboundResult

    async def handle_inbound_message(self, command: object) -> ConversationInboundResult:
        _ = command
        return self.result


class FakeMessagingAdapter:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[MessageTarget, OutboundMessage]] = []

    async def send_message(
        self,
        target: MessageTarget,
        content: OutboundMessage,
    ) -> SendResult:
        self.sent_messages.append((target, content))
        return SendResult(accepted=True, external_message_id="om_reply_1")


def build_event() -> InboundMessageEvent:
    return InboundMessageEvent(
        channel="feishu",
        event_type="im.message.receive_v1",
        chat_type="p2p",
        sender_open_id="ou_123",
        sender_user_id=None,
        sender_union_id=None,
        tenant_key=None,
        chat_id="oc_123",
        thread_id=None,
        message_id="om_123",
        root_message_id=None,
        parent_message_id=None,
        message_type="text",
        text="你好",
        raw_body={"text": "你好"},
    )


@pytest.mark.asyncio
async def test_inbound_event_recorder_sends_response_message_when_present() -> None:
    messaging_adapter = FakeMessagingAdapter()
    recorder = ConversationInboundEventRecorder(
        conversation_service=FakeConversationService(
            ConversationInboundResult(
                handled=True,
                conversation_id="conversation-1",
                session_id="session-1",
                handled_by="task",
                reason="task_created_via_llm",
                response_text="好的，已创建待办。",
            )
        ),
        messaging_adapter=messaging_adapter,
    )

    await recorder.record(build_event())

    assert messaging_adapter.sent_messages[0][0].recipient_id == "ou_123"
    assert messaging_adapter.sent_messages[0][1].text == "好的，已创建待办。"


@pytest.mark.asyncio
async def test_inbound_event_recorder_skips_response_when_no_response_text() -> None:
    messaging_adapter = FakeMessagingAdapter()
    recorder = ConversationInboundEventRecorder(
        conversation_service=FakeConversationService(
            ConversationInboundResult(
                handled=True,
                conversation_id="conversation-1",
                session_id="session-1",
                handled_by="task",
                reason="task_created_via_llm",
                response_text=None,
            )
        ),
        messaging_adapter=messaging_adapter,
    )

    await recorder.record(build_event())

    assert messaging_adapter.sent_messages == []


@pytest.mark.asyncio
async def test_inbound_event_recorder_sends_guidance_when_not_handled_but_has_response() -> None:
    messaging_adapter = FakeMessagingAdapter()
    recorder = ConversationInboundEventRecorder(
        conversation_service=FakeConversationService(
            ConversationInboundResult(
                handled=False,
                conversation_id="conversation-1",
                session_id="session-1",
                handled_by=None,
                reason="no_handler_accepted",
                response_text="我暂时没理解这条消息。",
            )
        ),
        messaging_adapter=messaging_adapter,
    )

    await recorder.record(build_event())

    assert messaging_adapter.sent_messages[0][1].text == "我暂时没理解这条消息。"
