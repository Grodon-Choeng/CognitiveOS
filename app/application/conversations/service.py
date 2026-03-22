from time import perf_counter

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.conversations.handlers import ConversationInboundHandler
from app.application.conversations.ports import ConversationContextResolver
from app.observability.message_events import MessageEventRecord, MessageEventRecorder


class ConversationApplicationService:
    def __init__(
        self,
        conversation_context_resolver: ConversationContextResolver,
        message_event_recorder: MessageEventRecorder,
        handlers: list[ConversationInboundHandler],
    ) -> None:
        self.conversation_context_resolver = conversation_context_resolver
        self.message_event_recorder = message_event_recorder
        self.handlers = handlers

    async def handle_inbound_message(
        self,
        command: HandleInboundConversationMessageCommand,
    ) -> ConversationInboundResult:
        conversation_context = await self.conversation_context_resolver.resolve_for_inbound(
            source_channel=command.channel,
            source_user_id=command.user_identity,
            source_chat_id=command.chat_id,
            source_thread_id=command.thread_id,
        )
        started_at = perf_counter()

        try:
            result = await self._dispatch_to_handlers(
                command=command,
                conversation_id=conversation_context.conversation_id,
                session_id=conversation_context.session_id,
            )
        except Exception as exc:
            await self.message_event_recorder.record(
                _build_inbound_record(
                    command=command,
                    conversation_id=conversation_context.conversation_id,
                    session_id=conversation_context.session_id,
                    handled=False,
                    handled_by=None,
                    reason="handler_exception",
                    response_text=None,
                    success=False,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                    latency_ms=(perf_counter() - started_at) * 1000,
                )
            )
            raise

        await self.message_event_recorder.record(
            _build_inbound_record(
                command=command,
                conversation_id=conversation_context.conversation_id,
                session_id=conversation_context.session_id,
                handled=result.handled,
                handled_by=result.handled_by,
                reason=result.reason,
                response_text=result.response_text,
                success=True,
                error_code=None,
                error_message=None,
                latency_ms=(perf_counter() - started_at) * 1000,
            )
        )
        return result

    async def _dispatch_to_handlers(
        self,
        *,
        command: HandleInboundConversationMessageCommand,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult:
        for handler in self.handlers:
            result = await handler.handle(
                command,
                conversation_id=conversation_id,
                session_id=session_id,
            )
            if result is not None and result.handled:
                return result

        return ConversationInboundResult(
            handled=False,
            conversation_id=conversation_id,
            session_id=session_id,
            handled_by=None,
            reason="no_handler_accepted",
        )


def _build_inbound_record(
    *,
    command: HandleInboundConversationMessageCommand,
    conversation_id: str,
    session_id: str,
    handled: bool,
    handled_by: str | None,
    reason: str | None,
    response_text: str | None,
    success: bool,
    error_code: str | None,
    error_message: str | None,
    latency_ms: float,
) -> MessageEventRecord:
    return MessageEventRecord.create(
        direction="inbound",
        channel=command.channel,
        message_type=command.message_type,
        user_identity=command.user_identity,
        external_message_id=command.external_message_id,
        root_message_id=command.root_message_id,
        parent_message_id=command.parent_message_id,
        chat_id=command.chat_id,
        thread_id=command.thread_id,
        conversation_id=conversation_id,
        session_id=session_id,
        trace_id=None,
        chain_id=None,
        request_id=None,
        latency_ms=latency_ms,
        text=command.text,
        success=success,
        error_code=error_code,
        error_message=error_message,
        raw_payload=command.raw_payload,
        metadata={
            "handled": handled,
            "handled_by": handled_by,
            "reason": reason,
            "response_text": response_text,
        },
    )
