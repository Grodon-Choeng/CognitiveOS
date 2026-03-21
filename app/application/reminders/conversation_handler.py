from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.reminders.commands import HandleReminderInboundMessageCommand
from app.application.reminders.service import ReminderApplicationService


class ReminderConversationHandler:
    name = "reminder"

    def __init__(self, reminder_service: ReminderApplicationService) -> None:
        self.reminder_service = reminder_service

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult | None:
        result = await self.reminder_service.handle_inbound_message(
            HandleReminderInboundMessageCommand(
                conversation_id=conversation_id,
                session_id=session_id,
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
            handled=result.handled,
            conversation_id=conversation_id,
            session_id=session_id,
            handled_by=self.name if result.handled else None,
            reason=result.reason,
        )
