from uuid import uuid4

from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    MessagingAdapter,
    OutboundMessage,
    SendResult,
)


class DebugIMMessagingAdapter(MessagingAdapter):
    async def send_message(
        self,
        target: MessageTarget,
        content: OutboundMessage,
    ) -> SendResult:
        _ = (target, content)
        return SendResult(
            accepted=True,
            external_message_id=f"dbgout_{uuid4()}",
            metadata={"adapter": "debug_im"},
        )
