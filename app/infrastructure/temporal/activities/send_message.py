from temporalio import activity

from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    MessagingAdapter,
    OutboundMessage,
)


class ReminderActivities:
    def __init__(self, messaging_adapter: MessagingAdapter) -> None:
        self.messaging_adapter = messaging_adapter

    @activity.defn(name="send-reminder-message")
    async def send_reminder_message(
        self,
        reminder_id: str,
        text: str,
        dispatch_channel: str,
        dispatch_recipient_id: str,
    ) -> str:
        activity.logger.info(
            "开始发送提醒消息。",
            extra={
                "reminder_id": reminder_id,
                "dispatch_channel": dispatch_channel,
                "dispatch_recipient_id": dispatch_recipient_id,
            },
        )
        result = await self.messaging_adapter.send_message(
            target=MessageTarget(
                channel=dispatch_channel,
                recipient_id=dispatch_recipient_id,
            ),
            content=OutboundMessage(
                text=text,
                metadata={"reminder_id": reminder_id},
            ),
        )
        activity.logger.info(
            "提醒消息发送完成。",
            extra={
                "reminder_id": reminder_id,
                "external_message_id": result.external_message_id,
            },
        )
        return result.external_message_id or ""
