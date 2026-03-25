from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.conversations.service import ConversationApplicationService
from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    MessagingAdapter,
    OutboundMessage,
)
from app.observability.context import (
    current_trace_fields,
    ensure_observability_context,
    reset_observability_context,
)


class ConversationInboundProcessor:
    def __init__(
        self,
        conversation_service: ConversationApplicationService,
        messaging_adapter: MessagingAdapter,
    ) -> None:
        self.conversation_service = conversation_service
        self.messaging_adapter = messaging_adapter

    async def handle_message(
        self,
        command: HandleInboundConversationMessageCommand,
    ) -> ConversationInboundResult:
        token = ensure_observability_context()
        try:
            result = await self.conversation_service.handle_inbound_message(command)
            if result.response_text is None:
                return result

            trace_id, chain_id, request_id = current_trace_fields()
            await self.messaging_adapter.send_message(
                MessageTarget(
                    channel=command.channel,
                    recipient_id=command.user_identity,
                ),
                OutboundMessage(
                    text=result.response_text,
                    metadata={
                        "conversation_id": result.conversation_id,
                        "session_id": result.session_id,
                        "chat_id": command.chat_id,
                        "thread_id": command.thread_id,
                        "parent_message_id": command.external_message_id,
                        "root_message_id": command.root_message_id or command.external_message_id,
                        "trace_id": trace_id,
                        "chain_id": chain_id,
                        "request_id": request_id,
                    },
                ),
            )
            return result
        finally:
            if token is not None:
                reset_observability_context(token)
