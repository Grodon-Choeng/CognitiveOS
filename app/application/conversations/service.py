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

        await self.message_event_recorder.record(
            MessageEventRecord.create(
                direction="inbound",
                channel=command.channel,
                message_type=command.message_type,
                user_identity=command.user_identity,
                external_message_id=command.external_message_id,
                root_message_id=command.root_message_id,
                parent_message_id=command.parent_message_id,
                chat_id=command.chat_id,
                thread_id=command.thread_id,
                conversation_id=conversation_context.conversation_id,
                session_id=conversation_context.session_id,
                trace_id=None,
                chain_id=None,
                request_id=None,
                text=command.text,
                raw_payload=command.raw_payload,
            )
        )

        for handler in self.handlers:
            result = await handler.handle(
                command,
                conversation_id=conversation_context.conversation_id,
                session_id=conversation_context.session_id,
            )
            if result is not None and result.handled:
                return result

        return ConversationInboundResult(
            handled=False,
            conversation_id=conversation_context.conversation_id,
            session_id=conversation_context.session_id,
            handled_by=None,
            reason="no_handler_accepted",
        )
