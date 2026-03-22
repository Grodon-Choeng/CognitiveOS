import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.conversations.ports import (
    ConversationContextResolver,
    ResolvedConversationContext,
)
from app.application.conversations.service import ConversationApplicationService
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
        self.records: list[object] = []

    async def record(self, record: object) -> None:
        self.records.append(record)


class DecliningHandler:
    name = "decline"

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult | None:
        _ = (command, conversation_id, session_id)
        return None


class AcceptingHandler:
    name = "accept"

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult | None:
        _ = command
        return ConversationInboundResult(
            handled=True,
            conversation_id=conversation_id,
            session_id=session_id,
            handled_by=self.name,
            response_text="好的，已处理。",
        )


@pytest.mark.asyncio
async def test_conversation_service_routes_to_first_accepting_handler() -> None:
    recorder = FakeMessageEventRecorder()
    service = ConversationApplicationService(
        conversation_context_resolver=FakeConversationContextResolver(),
        message_event_recorder=recorder,
        handlers=[DecliningHandler(), AcceptingHandler()],
    )

    result = await service.handle_inbound_message(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="你好",
            raw_payload={"text": "你好"},
        )
    )

    assert result.handled is True
    assert result.handled_by == "accept"
    assert result.conversation_id == "conversation-test"
    assert len(recorder.records) == 1
    record = recorder.records[0]
    assert isinstance(record, MessageEventRecord)
    assert record.metadata["handled"] is True
    assert record.metadata["handled_by"] == "accept"
    assert record.metadata["response_text"] == "好的，已处理。"
    assert isinstance(record.latency_ms, float)


@pytest.mark.asyncio
async def test_conversation_service_returns_no_handler_when_nobody_handles() -> None:
    recorder = FakeMessageEventRecorder()
    service = ConversationApplicationService(
        conversation_context_resolver=FakeConversationContextResolver(),
        message_event_recorder=recorder,
        handlers=[DecliningHandler()],
    )

    result = await service.handle_inbound_message(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="你好",
            raw_payload={"text": "你好"},
        )
    )

    assert result.handled is False
    assert result.reason == "no_handler_accepted"
    record = recorder.records[0]
    assert isinstance(record, MessageEventRecord)
    assert record.metadata["handled"] is False
    assert record.metadata["reason"] == "no_handler_accepted"


class ErrorHandler:
    name = "error"

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult | None:
        _ = (command, conversation_id, session_id)
        raise RuntimeError("处理失败")


@pytest.mark.asyncio
async def test_conversation_service_records_failure_when_handler_raises() -> None:
    recorder = FakeMessageEventRecorder()
    service = ConversationApplicationService(
        conversation_context_resolver=FakeConversationContextResolver(),
        message_event_recorder=recorder,
        handlers=[ErrorHandler()],
    )

    with pytest.raises(RuntimeError):
        await service.handle_inbound_message(
            HandleInboundConversationMessageCommand(
                channel="web",
                message_type="text",
                user_identity="user-1",
                external_message_id=None,
                root_message_id=None,
                parent_message_id=None,
                chat_id=None,
                thread_id=None,
                text="你好",
                raw_payload={"text": "你好"},
            )
        )

    record = recorder.records[0]
    assert isinstance(record, MessageEventRecord)
    assert record.success is False
    assert record.error_code == "RuntimeError"
    assert record.metadata["reason"] == "handler_exception"
