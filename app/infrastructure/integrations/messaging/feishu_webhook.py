import json
import logging
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Protocol

from app.config.settings import Settings
from app.infrastructure.types import JSONObject


class RawRequestProtocol(Protocol):
    headers: dict[str, str]
    body: bytes
    uri: str


@dataclass(slots=True, frozen=True)
class InboundMessageEvent:
    channel: str
    event_type: str
    message_id: str | None
    chat_id: str | None
    thread_id: str | None
    chat_type: str | None
    message_type: str | None
    text: str | None
    sender_open_id: str | None
    sender_user_id: str | None
    sender_union_id: str | None
    tenant_key: str | None
    raw_body: JSONObject


class FeishuInboundEventRecorder(Protocol):
    async def record(self, event: InboundMessageEvent) -> None: ...


class NoopFeishuInboundEventRecorder:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    async def record(self, event: InboundMessageEvent) -> None:
        self.logger.info(
            "收到飞书入站消息事件。",
            extra={
                "event_type": event.event_type,
                "message_id": event.message_id,
                "chat_id": event.chat_id,
                "sender_open_id": event.sender_open_id,
            },
        )


class FeishuWebhookHandler:
    def __init__(
        self,
        settings: Settings,
        inbound_event_recorder: FeishuInboundEventRecorder | None = None,
        dispatcher: Any | None = None,
    ) -> None:
        self.settings = settings
        self.inbound_event_recorder = inbound_event_recorder or NoopFeishuInboundEventRecorder()
        self.logger = logging.getLogger(__name__)
        self.dispatcher = dispatcher or self._build_dispatcher(settings)

    async def handle(self, request: RawRequestProtocol) -> tuple[int, JSONObject]:
        response = self.dispatcher.do(request)
        payload = self._decode_response_payload(response.content or b"{}")

        if request.body:
            await self._record_if_message_event(request.body)

        return response.status_code, payload

    def _build_dispatcher(self, settings: Settings) -> Any:
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            raise ValueError("飞书配置缺失：需要提供 FEISHU_APP_ID 和 FEISHU_APP_SECRET。")
        if not settings.feishu_verification_token:
            raise ValueError("飞书配置缺失：需要提供 FEISHU_VERIFICATION_TOKEN。")

        lark: Any = import_module("lark_oapi")
        encrypt_key = settings.feishu_encrypt_key or ""
        return (
            lark.EventDispatcherHandler.builder(
                encrypt_key=encrypt_key,
                verification_token=settings.feishu_verification_token,
            )
            .register_p2_im_message_receive_v1(self._handle_message_event)
            .build()
        )

    def _handle_message_event(self, data: Any) -> None:
        event = self._normalize_message_event(data)
        self.logger.info(
            "飞书事件分发器收到消息事件。",
            extra={
                "event_type": event.event_type,
                "message_id": event.message_id,
                "chat_id": event.chat_id,
                "sender_open_id": event.sender_open_id,
            },
        )

    async def _record_if_message_event(self, body: bytes) -> None:
        payload = self._decode_response_payload(body)
        header = payload.get("header")
        if not isinstance(header, dict):
            return

        event_type = header.get("event_type")
        if event_type != "im.message.receive_v1":
            return

        event = self._normalize_message_event_from_payload(payload)
        await self.inbound_event_recorder.record(event)

    def _normalize_message_event(self, data: Any) -> InboundMessageEvent:
        payload = json.loads(json.dumps(data, default=lambda value: value.__dict__))
        return self._normalize_message_event_from_payload(payload)

    def _normalize_message_event_from_payload(
        self,
        payload: JSONObject,
    ) -> InboundMessageEvent:
        event = payload.get("event")
        sender = event.get("sender") if isinstance(event, dict) else {}
        sender_id = sender.get("sender_id") if isinstance(sender, dict) else {}
        message = event.get("message") if isinstance(event, dict) else {}

        text = None
        if isinstance(message, dict):
            raw_content = message.get("content")
            if isinstance(raw_content, str):
                try:
                    content_json = json.loads(raw_content)
                except json.JSONDecodeError:
                    content_json = {}
                if isinstance(content_json, dict):
                    raw_text = content_json.get("text")
                    if isinstance(raw_text, str):
                        text = raw_text

        return InboundMessageEvent(
            channel="feishu",
            event_type="im.message.receive_v1",
            message_id=self._get_optional_string(message, "message_id"),
            chat_id=self._get_optional_string(message, "chat_id"),
            thread_id=self._get_optional_string(message, "thread_id"),
            chat_type=self._get_optional_string(message, "chat_type"),
            message_type=self._get_optional_string(message, "message_type"),
            text=text,
            sender_open_id=self._get_optional_string(sender_id, "open_id"),
            sender_user_id=self._get_optional_string(sender_id, "user_id"),
            sender_union_id=self._get_optional_string(sender_id, "union_id"),
            tenant_key=self._get_optional_string(sender, "tenant_key"),
            raw_body=payload,
        )

    @staticmethod
    def _decode_response_payload(content: bytes) -> JSONObject:
        if not content:
            return {}
        return json.loads(content.decode("utf-8"))

    @staticmethod
    def _get_optional_string(payload: object, key: str) -> str | None:
        if not isinstance(payload, dict):
            return None

        value = payload.get(key)
        if isinstance(value, str):
            return value
        return None
