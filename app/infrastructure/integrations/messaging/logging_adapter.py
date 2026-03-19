import logging

from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    MessagingAdapter,
    OutboundMessage,
    SendResult,
)


class LoggingMessagingAdapter(MessagingAdapter):
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    async def send_message(
        self,
        target: MessageTarget,
        content: OutboundMessage,
    ) -> SendResult:
        self.logger.info(
            "通过日志适配器发送提醒消息。",
            extra={
                "channel": target.channel,
                "recipient_id": target.recipient_id,
                "text": content.text,
            },
        )
        return SendResult(
            accepted=True,
            external_message_id=f"log:{target.channel}:{target.recipient_id}",
            metadata={"adapter": "logging"},
        )
