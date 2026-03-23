import pytest

from app.application.audit.dto import AuditEventDTO, AuditEventPageDTO
from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.conversations.ports import (
    ConversationContextResolver,
    ResolvedConversationContext,
)
from app.application.conversations.service import (
    ConversationApplicationService,
    LLMConversationFallbackResponder,
)
from app.infrastructure.llm.models import GenerateRequest, GenerateResult
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


class FakeHistoryReader:
    async def list_events(
        self,
        *,
        kind: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        success: bool | None = None,
        channel: str | None = None,
        provider: str | None = None,
        tool_name: str | None = None,
        workflow_type: str | None = None,
        recorded_after: object | None = None,
        recorded_before: object | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditEventPageDTO:
        _ = (
            kind,
            conversation_id,
            session_id,
            success,
            channel,
            provider,
            tool_name,
            workflow_type,
            recorded_after,
            recorded_before,
            cursor,
            limit,
        )
        return AuditEventPageDTO(
            items=[
                AuditEventDTO(
                    kind="message",
                    event_id="evt-0",
                    recorded_at="2026-03-23T11:59:00+08:00",
                    conversation_id="conversation-test",
                    session_id="session-test",
                    trace_id=None,
                    chain_id=None,
                    request_id=None,
                    success=True,
                    summary="inbound:feishu:text",
                    payload={"direction": "inbound", "text": "hey"},
                ),
                AuditEventDTO(
                    kind="message",
                    event_id="evt-1",
                    recorded_at="2026-03-23T12:00:00+08:00",
                    conversation_id="conversation-test",
                    session_id="session-test",
                    trace_id=None,
                    chain_id=None,
                    request_id=None,
                    success=True,
                    summary="outbound:feishu:text",
                    payload={"direction": "outbound", "text": "你好，我可以帮你记提醒和待办。"},
                )
            ]
        )


class FakeFallbackLLMGateway:
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
    assert "我还没听懂这句话" in (result.response_text or "")
    record = recorder.records[0]
    assert isinstance(record, MessageEventRecord)
    assert record.metadata["handled"] is False
    assert record.metadata["reason"] == "no_handler_accepted"
    response_text = record.metadata["response_text"]
    assert isinstance(response_text, str)
    assert "你可以帮我做什么" in response_text


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


@pytest.mark.asyncio
async def test_conversation_service_uses_llm_fallback_reply_when_no_handler_accepts() -> None:
    recorder = FakeMessageEventRecorder()
    fallback_gateway = FakeFallbackLLMGateway(
        '{"reply_text":"是的，我现在主要帮你处理提醒、待办和记忆。"}'
    )
    service = ConversationApplicationService(
        conversation_context_resolver=FakeConversationContextResolver(),
        message_event_recorder=recorder,
        handlers=[DecliningHandler()],
        fallback_responder=LLMConversationFallbackResponder(
            llm_gateway=fallback_gateway,
            model="gpt-test",
            api_key_suffix="90abcdef",
            history_reader=FakeHistoryReader(),
        ),
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
            text="是吗？",
            raw_payload={"text": "是吗？"},
        )
    )

    assert result.handled is True
    assert result.handled_by == "conversation"
    assert result.reason == "llm_fallback_replied"
    assert result.response_text == "是的，我现在主要帮你处理提醒、待办和记忆。"
    assert fallback_gateway.last_request is not None
    assert "最近对话：" in fallback_gateway.last_request.prompt
    assert "user: hey" in fallback_gateway.last_request.prompt
    assert "assistant: 你好，我可以帮你记提醒和待办。" in fallback_gateway.last_request.prompt
    assert "当前用户消息：是吗？" in fallback_gateway.last_request.prompt
    record = recorder.records[0]
    assert isinstance(record, MessageEventRecord)
    assert record.metadata["handled"] is True
    assert record.metadata["reason"] == "llm_fallback_replied"
