from dataclasses import dataclass

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.conversations.inbound_processor import ConversationInboundProcessor
from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    OutboundMessage,
    SendResult,
)


@dataclass
class FakeConversationService:
    result: ConversationInboundResult

    async def handle_inbound_message(
        self,
        command: HandleInboundConversationMessageCommand,
    ) -> ConversationInboundResult:
        self.command = command
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
        return SendResult(accepted=True, external_message_id="dbgout_1")


@pytest.mark.asyncio
async def test_conversation_inbound_processor_sends_response_message() -> None:
    messaging_adapter = FakeMessagingAdapter()
    processor = ConversationInboundProcessor(
        conversation_service=FakeConversationService(
            ConversationInboundResult(
                handled=True,
                conversation_id="conversation-1",
                session_id="session-1",
                handled_by="conversation",
                reason="handled",
                response_text="你好，我在。",
            )
        ),
        messaging_adapter=messaging_adapter,
    )

    result = await processor.handle_message(
        HandleInboundConversationMessageCommand(
            channel="debug_im",
            message_type="text",
            user_identity="debug-user",
            external_message_id="dbgmsg_1",
            root_message_id="dbgroot_1",
            parent_message_id=None,
            chat_id="chat-1",
            thread_id=None,
            text="你好",
            raw_payload={"text": "你好"},
        )
    )

    assert result.response_text == "你好，我在。"
    assert messaging_adapter.sent_messages[0][0].channel == "debug_im"
    assert messaging_adapter.sent_messages[0][0].recipient_id == "debug-user"
    assert messaging_adapter.sent_messages[0][1].metadata["parent_message_id"] == "dbgmsg_1"
    assert messaging_adapter.sent_messages[0][1].metadata["root_message_id"] == "dbgroot_1"


@pytest.mark.asyncio
async def test_conversation_inbound_processor_skips_send_when_no_response_text() -> None:
    messaging_adapter = FakeMessagingAdapter()
    processor = ConversationInboundProcessor(
        conversation_service=FakeConversationService(
            ConversationInboundResult(
                handled=False,
                conversation_id="conversation-1",
                session_id="session-1",
                handled_by=None,
                reason="no_handler_accepted",
                response_text=None,
            )
        ),
        messaging_adapter=messaging_adapter,
    )

    await processor.handle_message(
        HandleInboundConversationMessageCommand(
            channel="debug_im",
            message_type="text",
            user_identity="debug-user",
            external_message_id="dbgmsg_1",
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="你好",
            raw_payload={"text": "你好"},
        )
    )

    assert messaging_adapter.sent_messages == []
