from app.config.settings import Settings
from app.infrastructure.integrations.messaging.feishu_long_connection import (
    FeishuLongConnectionListener,
)
from app.infrastructure.integrations.messaging.feishu_webhook import FeishuWebhookHandler


class FakeWsClient:
    def __init__(self) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True


class FakeDispatcher:
    def do(self, request: object) -> object:
        _ = request
        raise AssertionError("长连接测试不应直接调用 webhook do")


def test_feishu_long_connection_listener_starts_client() -> None:
    client = FakeWsClient()
    handler = FeishuWebhookHandler(
        settings=Settings(
            feishu_app_id="cli_test",
            feishu_app_secret="secret_test",
            feishu_verification_token="verification-token",
        ),
        dispatcher=FakeDispatcher(),
    )
    listener = FeishuLongConnectionListener(
        settings=Settings(
            feishu_app_id="cli_test",
            feishu_app_secret="secret_test",
            feishu_verification_token="verification-token",
        ),
        webhook_handler=handler,
        client=client,
    )

    listener.start()

    assert client.started is True
