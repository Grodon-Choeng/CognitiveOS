import logging

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.service import ConversationApplicationService
from app.infrastructure.integrations.messaging.feishu_webhook import (
    FeishuInboundEventRecorder,
    InboundMessageEvent,
)


class ConversationInboundEventRecorder(FeishuInboundEventRecorder):
    def __init__(self, conversation_service: ConversationApplicationService) -> None:
        self.conversation_service = conversation_service
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

        result = await self.conversation_service.handle_inbound_message(
            HandleInboundConversationMessageCommand(
                channel=event.channel,
                message_type=event.message_type or "text",
                user_identity=event.sender_open_id,
                external_message_id=event.message_id,
                root_message_id=event.root_message_id,
                parent_message_id=event.parent_message_id,
                chat_id=event.chat_id,
                thread_id=event.thread_id,
                text=event.text,
                raw_payload=event.raw_body,
            )
        )
        self.logger.info(
            "飞书入站消息处理完成。",
            extra={
                "message_id": event.message_id,
                "handled": result.handled,
                "conversation_id": result.conversation_id,
                "session_id": result.session_id,
                "handled_by": result.handled_by,
                "reason": result.reason,
            },
        )
