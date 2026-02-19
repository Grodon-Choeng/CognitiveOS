from app.config import IMProvider
from .base import IMAdapter, IMMessage, IMSendResult, MessageType
from .wecom import WeComAdapter
from .dingtalk import DingTalkAdapter
from .feishu import FeishuAdapter
from .discord import DiscordAdapter


def create_adapter(
    provider: IMProvider, webhook_url: str, secret: str = ""
) -> IMAdapter:
    adapters = {
        IMProvider.WECOM: WeComAdapter,
        IMProvider.DINGTALK: DingTalkAdapter,
        IMProvider.FEISHU: FeishuAdapter,
        IMProvider.DISCORD: DiscordAdapter,
    }

    adapter_class = adapters.get(provider)
    if not adapter_class:
        raise ValueError(f"Unknown IM provider: {provider}")

    if provider in (IMProvider.DINGTALK, IMProvider.FEISHU):
        return adapter_class(webhook_url=webhook_url, secret=secret)

    return adapter_class(webhook_url=webhook_url)


__all__ = [
    "IMAdapter",
    "IMMessage",
    "IMSendResult",
    "MessageType",
    "IMProvider",
    "WeComAdapter",
    "DingTalkAdapter",
    "FeishuAdapter",
    "DiscordAdapter",
    "create_adapter",
]
