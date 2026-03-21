import logging

from app.application.reminders.commands import HandleReminderInboundMessageCommand
from app.application.reminders.service import ReminderApplicationService
from app.infrastructure.integrations.messaging.feishu_webhook import (
    FeishuInboundEventRecorder,
    InboundMessageEvent,
)


class ReminderInboundEventRecorder(FeishuInboundEventRecorder):
    def __init__(self, reminder_service: ReminderApplicationService) -> None:
        self.reminder_service = reminder_service
        self.logger = logging.getLogger(__name__)

    async def record(self, event: InboundMessageEvent) -> None:
        if event.channel != "feishu":
            return
        if event.chat_type != "p2p":
            self.logger.info(
                "忽略非 p2p 飞书入站消息。",
                extra={"chat_type": event.chat_type, "message_id": event.message_id},
            )
            return
        if not event.sender_open_id or not event.text:
            self.logger.info(
                "忽略缺少 sender_open_id 或文本内容的飞书入站消息。",
                extra={"message_id": event.message_id},
            )
            return

        result = await self.reminder_service.handle_inbound_message(
            HandleReminderInboundMessageCommand(
                conversation_id=None,
                session_id=None,
                channel=event.channel,
                sender_id=event.sender_open_id,
                message_id=event.message_id,
                root_message_id=event.root_message_id,
                parent_message_id=event.parent_message_id,
                chat_id=event.chat_id,
                thread_id=event.thread_id,
                text=event.text,
            )
        )
        self.logger.info(
            "飞书入站消息处理完成。",
            extra={
                "message_id": event.message_id,
                "handled": result.handled,
                "reminder_id": result.reminder_id,
                "reason": result.reason,
            },
        )
