from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationFastPathResult
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
    ) -> ConversationFastPathResult:
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

        assistant_turn_state = None
        if result.decision == "completed":
            assistant_turn_state = {
                "dialogue_mode": "normal",
                "last_assistant_action": {
                    "action_type": "reply_reminder",
                    "success": True,
                    "object_type": "reminder",
                    "object_id": result.reminder_id,
                    "summary": result.response_text or "提醒续执行已完成",
                },
            }
        elif result.decision == "needs_confirmation":
            assistant_turn_state = {
                "dialogue_mode": "confirmation",
                "pending_confirmation": {
                    "confirm_action": "reply_reminder",
                    "preview_text": "最近提醒回复",
                },
                "last_assistant_action": {
                    "action_type": "reply_reminder_needs_confirmation",
                    "success": True,
                    "object_type": "reminder",
                    "object_id": result.reminder_id,
                    "summary": result.response_text,
                },
            }

        return ConversationFastPathResult(
            decision=result.decision,
            conversation_id=conversation_id,
            session_id=session_id,
            handled_by=self.name if result.decision != "pass_to_kernel" else None,
            reason=result.reason,
            response_text=result.response_text,
            assistant_turn_state=assistant_turn_state,
            debug={
                "stage": "reminder_fast_path",
                "decision": result.decision,
                "reason": result.reason,
                "match_source": result.match_source,
                "response_text": result.response_text,
            },
        )
