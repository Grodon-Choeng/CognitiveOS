import json
from dataclasses import dataclass

import pytest

from app.config.settings import Settings
from app.infrastructure.integrations.messaging.feishu_webhook import (
    FeishuWebhookHandler,
    InboundMessageEvent,
)
from app.infrastructure.types import JSONObject


class FakeInboundRecorder:
    def __init__(self) -> None:
        self.events: list[InboundMessageEvent] = []

    async def record(self, event: InboundMessageEvent) -> None:
        self.events.append(event)


@dataclass
class FakeRawResponse:
    status_code: int
    content: bytes


class FakeDispatcher:
    def __init__(self, response_payload: JSONObject) -> None:
        self.response_payload = response_payload
        self.requests: list[object] = []

    def do(self, request: object) -> FakeRawResponse:
        self.requests.append(request)
        return FakeRawResponse(
            status_code=200,
            content=json.dumps(self.response_payload, ensure_ascii=False).encode("utf-8"),
        )


@dataclass
class FakeRawRequest:
    headers: dict[str, str]
    body: bytes
    uri: str


def build_message_event_payload() -> JSONObject:
    return {
        "schema": "2.0",
        "header": {
            "event_type": "im.message.receive_v1",
            "token": "verification-token",
        },
        "event": {
            "sender": {
                "sender_id": {
                    "open_id": "ou_123",
                    "user_id": "u_123",
                    "union_id": "on_123",
                },
                "sender_type": "user",
                "tenant_key": "tenant_123",
            },
            "message": {
                "message_id": "om_123",
                "root_id": "om_root_123",
                "parent_id": "om_parent_123",
                "chat_id": "oc_123",
                "thread_id": "ot_123",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": "你好"}),
            },
        },
    }


@pytest.mark.asyncio
async def test_feishu_webhook_handler_normalizes_message_event() -> None:
    recorder = FakeInboundRecorder()
    payload = build_message_event_payload()
    handler = FeishuWebhookHandler(
        settings=Settings(
            feishu_app_id="cli_test",
            feishu_app_secret="secret_test",
            feishu_verification_token="verification-token",
        ),
        inbound_event_recorder=recorder,
        dispatcher=FakeDispatcher({"challenge": "ok"}),
    )

    status_code, response = await handler.handle(
        FakeRawRequest(
            headers={},
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            uri="/api/v1/integrations/feishu/events",
        )
    )

    assert status_code == 200
    assert response["challenge"] == "ok"
    assert len(recorder.events) == 1
    event = recorder.events[0]
    assert event.channel == "feishu"
    assert event.message_id == "om_123"
    assert event.root_message_id == "om_root_123"
    assert event.parent_message_id == "om_parent_123"
    assert event.chat_id == "oc_123"
    assert event.thread_id == "ot_123"
    assert event.sender_open_id == "ou_123"
    assert event.text == "你好"


def test_feishu_webhook_handler_requires_verification_token() -> None:
    with pytest.raises(ValueError):
        FeishuWebhookHandler(
            settings=Settings(
                feishu_app_id="cli_test",
                feishu_app_secret="secret_test",
                feishu_verification_token=None,
            )
        )
