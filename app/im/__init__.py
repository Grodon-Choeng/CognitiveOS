from app.config import IMConfig
from app.enums import IMProvider

from .base import IMAdapter, IMMessage, IMSendResult, MessageType
from .dingtalk import DingTalkAdapter
from .discord import DiscordAdapter
from .feishu import FeishuAdapter
from .wecom import WeComAdapter


def create_adapter(config: IMConfig) -> IMAdapter:
    adapters = {
        IMProvider.WECOM: WeComAdapter,
        IMProvider.DINGTALK: DingTalkAdapter,
        IMProvider.FEISHU: FeishuAdapter,
        IMProvider.DISCORD: DiscordAdapter,
    }

    adapter_class = adapters.get(config.provider)
    if not adapter_class:
        raise ValueError(f"Unknown IM provider: {config.provider}")

    if config.provider in (IMProvider.DINGTALK, IMProvider.FEISHU):
        return adapter_class(webhook_url=config.webhook_url, secret=config.secret)

    return adapter_class(webhook_url=config.webhook_url)


class IMManager:
    def __init__(self, configs: list[IMConfig]) -> None:
        self._configs = {cfg.provider: cfg for cfg in configs}
        self._adapters: dict[IMProvider, IMAdapter] = {}

    def get_adapter(self, provider: IMProvider) -> IMAdapter | None:
        if provider in self._adapters:
            return self._adapters[provider]

        config = self._configs.get(provider)
        if not config or not config.enabled:
            return None

        adapter = create_adapter(config)
        self._adapters[provider] = adapter
        return adapter

    def get_all_adapters(self) -> list[IMAdapter]:
        adapters = []
        for provider in self._configs:
            adapter = self.get_adapter(provider)
            if adapter:
                adapters.append(adapter)
        return adapters

    def get_available_providers(self) -> list[IMProvider]:
        return [p for p, cfg in self._configs.items() if cfg.enabled]

    async def send_to_all(self, message: IMMessage) -> list[IMSendResult]:
        results = []
        for adapter in self.get_all_adapters():
            result = await adapter.send(message)
            results.append(result)
        return results

    async def send_to_provider(self, provider: IMProvider, message: IMMessage) -> IMSendResult:
        adapter = self.get_adapter(provider)
        if not adapter:
            return IMSendResult(success=False, error=f"IM provider {provider.value} not configured")
        return await adapter.send(message)


__all__ = [
    "IMAdapter",
    "IMMessage",
    "IMSendResult",
    "MessageType",
    "IMProvider",
    "IMConfig",
    "WeComAdapter",
    "DingTalkAdapter",
    "FeishuAdapter",
    "DiscordAdapter",
    "create_adapter",
    "IMManager",
]
