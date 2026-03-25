from dataclasses import dataclass

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.bootstrap.inbound_events import ConversationInboundEventRecorder
from app.infrastructure.integrations.messaging.feishu_webhook import InboundMessageEvent


@dataclass
class FakeInboundProcessor:
    result: ConversationInboundResult

    def __post_init__(self) -> None:
        self.commands: list[HandleInboundConversationMessageCommand] = []

    async def handle_message(
        self,
        command: HandleInboundConversationMessageCommand,
    ) -> ConversationInboundResult:
        self.commands.append(command)
        return self.result


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
async def test_inbound_event_recorder_delegates_valid_feishu_event() -> None:
    processor = FakeInboundProcessor(
        ConversationInboundResult(
            handled=True,
            conversation_id="conversation-1",
            session_id="session-1",
            handled_by="task",
            reason="task_created_via_llm",
            response_text="好的，已创建待办。",
        )
    )
    recorder = ConversationInboundEventRecorder(inbound_processor=processor)

    await recorder.record(build_event())

    assert processor.commands[0].channel == "feishu"
    assert processor.commands[0].user_identity == "ou_123"
    assert processor.commands[0].text == "你好"


@pytest.mark.asyncio
async def test_inbound_event_recorder_skips_non_p2p_message() -> None:
    processor = FakeInboundProcessor(
        ConversationInboundResult(
            handled=True,
            conversation_id="conversation-1",
            session_id="session-1",
            handled_by="conversation",
            reason="handled",
            response_text="ignored",
        )
    )
    recorder = ConversationInboundEventRecorder(inbound_processor=processor)
    event = build_event()
    event = InboundMessageEvent(
        channel=event.channel,
        event_type=event.event_type,
        message_id=event.message_id,
        root_message_id=event.root_message_id,
        parent_message_id=event.parent_message_id,
        chat_id=event.chat_id,
        thread_id=event.thread_id,
        chat_type="group",
        message_type=event.message_type,
        text=event.text,
        sender_open_id=event.sender_open_id,
        sender_user_id=event.sender_user_id,
        sender_union_id=event.sender_union_id,
        tenant_key=event.tenant_key,
        raw_body=event.raw_body,
    )

    await recorder.record(event)

    assert processor.commands == []


@pytest.mark.asyncio
async def test_inbound_event_recorder_skips_missing_sender_or_text() -> None:
    processor = FakeInboundProcessor(
        ConversationInboundResult(
            handled=True,
            conversation_id="conversation-1",
            session_id="session-1",
            handled_by="conversation",
            reason="handled",
            response_text="ignored",
        )
    )
    recorder = ConversationInboundEventRecorder(inbound_processor=processor)
    event = build_event()
    event = InboundMessageEvent(
        channel=event.channel,
        event_type=event.event_type,
        message_id=event.message_id,
        root_message_id=event.root_message_id,
        parent_message_id=event.parent_message_id,
        chat_id=event.chat_id,
        thread_id=event.thread_id,
        chat_type=event.chat_type,
        message_type=event.message_type,
        text=None,
        sender_open_id=event.sender_open_id,
        sender_user_id=event.sender_user_id,
        sender_union_id=event.sender_union_id,
        tenant_key=event.tenant_key,
        raw_body=event.raw_body,
    )

    await recorder.record(event)

    assert processor.commands == []
