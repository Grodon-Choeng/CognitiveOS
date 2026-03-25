from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    MessagingAdapter,
    OutboundMessage,
    SendResult,
)


class RoutingMessagingAdapter(MessagingAdapter):
    def __init__(
        self,
        *,
        default_adapter: MessagingAdapter,
        debug_im_adapter: MessagingAdapter | None = None,
        feishu_adapter: MessagingAdapter | None = None,
    ) -> None:
        self.default_adapter = default_adapter
        self.debug_im_adapter = debug_im_adapter
        self.feishu_adapter = feishu_adapter

    async def send_message(
        self,
        target: MessageTarget,
        content: OutboundMessage,
    ) -> SendResult:
        if target.channel == "debug_im":
            if self.debug_im_adapter is None:
                raise ValueError("未配置 debug_im 消息适配器，无法发送调试 IM 消息。")
            return await self.debug_im_adapter.send_message(target, content)
        if target.channel == "feishu":
            if self.feishu_adapter is None:
                raise ValueError("未配置飞书消息适配器，无法发送飞书消息。")
            return await self.feishu_adapter.send_message(target, content)

        return await self.default_adapter.send_message(target, content)
