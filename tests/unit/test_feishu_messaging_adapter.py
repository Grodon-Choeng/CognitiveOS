import json
from dataclasses import dataclass

import pytest

from app.config.settings import Settings
from app.infrastructure.integrations.messaging import (
    FeishuMessagingAdapter,
    LoggingMessagingAdapter,
    MessageTarget,
    OutboundMessage,
    RoutingMessagingAdapter,
)


@dataclass
class FakeRawResponse:
    content: bytes


class FakeFeishuSuccessResponse:
    def __init__(self) -> None:
        self.code = 0
        self.msg = "success"
        self.raw = FakeRawResponse(
            content=json.dumps(
                {"data": {"message_id": "om_123"}},
                ensure_ascii=False,
            ).encode("utf-8")
        )

    def success(self) -> bool:
        return True


class FakeFeishuFailureResponse:
    def __init__(self) -> None:
        self.code = 99991663
        self.msg = "invalid app credential"
        self.raw = FakeRawResponse(content=b"{}")

    def success(self) -> bool:
        return False


class FakeFeishuClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[object] = []

    def request(self, request: object) -> object:
        self.requests.append(request)
        return self.response


@pytest.mark.asyncio
async def test_feishu_adapter_sends_message_successfully() -> None:
    settings = Settings(
        feishu_app_id="cli_test",
        feishu_app_secret="secret_test",
    )
    client = FakeFeishuClient(FakeFeishuSuccessResponse())
    adapter = FeishuMessagingAdapter(settings=settings, client=client)

    result = await adapter.send_message(
        MessageTarget(channel="feishu", recipient_id="ou_xxx"),
        OutboundMessage(text="你好，飞书"),
    )

    assert result.accepted is True
    assert result.external_message_id == "om_123"
    assert result.metadata["receive_id_type"] == "open_id"
    assert len(client.requests) == 1


@pytest.mark.asyncio
async def test_feishu_adapter_raises_when_response_failed() -> None:
    settings = Settings(
        feishu_app_id="cli_test",
        feishu_app_secret="secret_test",
    )
    client = FakeFeishuClient(FakeFeishuFailureResponse())
    adapter = FeishuMessagingAdapter(settings=settings, client=client)

    with pytest.raises(RuntimeError):
        await adapter.send_message(
            MessageTarget(channel="feishu", recipient_id="ou_xxx"),
            OutboundMessage(text="你好，飞书"),
        )


@pytest.mark.asyncio
async def test_routing_adapter_routes_feishu_channel() -> None:
    settings = Settings(
        feishu_app_id="cli_test",
        feishu_app_secret="secret_test",
    )
    feishu_adapter = FeishuMessagingAdapter(
        settings=settings,
        client=FakeFeishuClient(FakeFeishuSuccessResponse()),
    )
    adapter = RoutingMessagingAdapter(
        default_adapter=LoggingMessagingAdapter(),
        feishu_adapter=feishu_adapter,
    )

    result = await adapter.send_message(
        MessageTarget(channel="feishu", recipient_id="ou_xxx"),
        OutboundMessage(text="测试路由"),
    )

    assert result.accepted is True
    assert result.external_message_id == "om_123"
