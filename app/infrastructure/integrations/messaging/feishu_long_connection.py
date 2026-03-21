from importlib import import_module
from typing import Any, Protocol

from app.config.settings import Settings
from app.infrastructure.integrations.messaging.feishu_webhook import FeishuWebhookHandler


class FeishuWsClientProtocol(Protocol):
    def start(self) -> None: ...


class FeishuLongConnectionListener:
    def __init__(
        self,
        settings: Settings,
        webhook_handler: FeishuWebhookHandler,
        client: FeishuWsClientProtocol | None = None,
    ) -> None:
        self.settings = settings
        self.webhook_handler = webhook_handler
        self.client = client or self._build_client(settings, webhook_handler)

    def start(self) -> None:
        self.client.start()

    @staticmethod
    def _build_client(
        settings: Settings,
        webhook_handler: FeishuWebhookHandler,
    ) -> FeishuWsClientProtocol:
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            raise ValueError("飞书配置缺失：需要提供 FEISHU_APP_ID 和 FEISHU_APP_SECRET。")

        lark: Any = import_module("lark_oapi")
        return lark.ws.Client(
            app_id=settings.feishu_app_id,
            app_secret=settings.feishu_app_secret,
            event_handler=webhook_handler.dispatcher,
            auto_reconnect=True,
        )
