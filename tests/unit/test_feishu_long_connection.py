import pytest

from app.config.settings import Settings
from app.infrastructure.integrations.messaging.feishu_long_connection import (
    FeishuLongConnectionListener,
)
from app.infrastructure.integrations.messaging.feishu_webhook import FeishuWebhookHandler


class FakeWsClient:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    async def _disconnect(self) -> None:
        self.stopped = True


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


def test_feishu_long_connection_listener_stops_client_when_supported() -> None:
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

    import asyncio

    asyncio.run(listener.stop())

    assert client.stopped is True


def test_bind_feishu_ws_client_loop_ignores_missing_lark_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.bootstrap import feishu_long_connection

    fake_loop = object()

    def raise_missing_sdk(module_name: str) -> object:
        _ = module_name
        raise ModuleNotFoundError("No module named 'lark_oapi'", name="lark_oapi")

    monkeypatch.setattr(feishu_long_connection, "import_module", raise_missing_sdk)

    feishu_long_connection._bind_feishu_ws_client_loop(fake_loop)  # type: ignore[arg-type]


def test_bind_feishu_ws_client_loop_reraises_unexpected_missing_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.bootstrap import feishu_long_connection

    def raise_unexpected_dependency(module_name: str) -> object:
        _ = module_name
        raise ModuleNotFoundError("No module named 'httpx'", name="httpx")

    monkeypatch.setattr(feishu_long_connection, "import_module", raise_unexpected_dependency)

    with pytest.raises(ModuleNotFoundError, match="httpx"):
        feishu_long_connection._bind_feishu_ws_client_loop(object())  # type: ignore[arg-type]
