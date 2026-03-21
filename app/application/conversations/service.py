from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.conversations.ports import ConversationContextResolver
from app.application.reminders.commands import HandleReminderInboundMessageCommand
from app.application.reminders.service import ReminderApplicationService
from app.observability.message_events import MessageEventRecord, MessageEventRecorder


class ConversationApplicationService:
    def __init__(
        self,
        conversation_context_resolver: ConversationContextResolver,
        reminder_service: ReminderApplicationService,
        message_event_recorder: MessageEventRecorder,
    ) -> None:
        self.conversation_context_resolver = conversation_context_resolver
        self.reminder_service = reminder_service
        self.message_event_recorder = message_event_recorder

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

        reminder_result = await self.reminder_service.handle_inbound_message(
            HandleReminderInboundMessageCommand(
                conversation_id=conversation_context.conversation_id,
                session_id=conversation_context.session_id,
                channel=command.channel,
                sender_id=command.user_identity,
                message_id=command.external_message_id,
                root_message_id=command.root_message_id,
                parent_message_id=command.parent_message_id,
                chat_id=command.chat_id,
                thread_id=command.thread_id,
                text=command.text or "",
            )
        )

        return ConversationInboundResult(
            handled=reminder_result.handled,
            conversation_id=conversation_context.conversation_id,
            session_id=conversation_context.session_id,
            handled_by="reminder" if reminder_result.handled else None,
            reason=reminder_result.reason,
        )
