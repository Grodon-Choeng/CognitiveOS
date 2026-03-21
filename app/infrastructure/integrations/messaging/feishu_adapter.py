import asyncio
import json
import logging
from importlib import import_module
from typing import Any, Protocol

from app.config.settings import Settings
from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    MessagingAdapter,
    OutboundMessage,
    SendResult,
)
from app.infrastructure.types import JSONObject


class FeishuClientProtocol(Protocol):
    def request(self, request: Any) -> Any: ...


class FeishuMessagingAdapter(MessagingAdapter):
    def __init__(
        self,
        settings: Settings,
        client: FeishuClientProtocol | None = None,
    ) -> None:
        self.settings = settings
        self.client = client or self._build_client(settings)
        self.logger = logging.getLogger(__name__)

    async def send_message(
        self,
        target: MessageTarget,
        content: OutboundMessage,
    ) -> SendResult:
        receive_id_type = self._resolve_receive_id_type(target, content)
        request = self._build_message_request(
            receive_id=target.recipient_id,
            receive_id_type=receive_id_type,
            content=content,
        )
        response = await asyncio.to_thread(self.client.request, request)

        if not response.success():
            error_code = str(getattr(response, "code", "unknown"))
            error_message = str(getattr(response, "msg", "飞书消息发送失败"))
            self.logger.error(
                "飞书消息发送失败。",
                extra={
                    "receive_id_type": receive_id_type,
                    "recipient_id": target.recipient_id,
                    "error_code": error_code,
                    "error_message": error_message,
                },
            )
            raise RuntimeError(f"飞书消息发送失败：{error_code} {error_message}")

        response_body = self._load_response_body(response)
        message_id = self._extract_message_id(response_body)
        metadata: JSONObject = {
            "adapter": "feishu",
            "channel": "feishu",
            "receive_id_type": receive_id_type,
            "response_body": response_body,
        }
        self.logger.info(
            "飞书消息发送成功。",
            extra={
                "receive_id_type": receive_id_type,
                "recipient_id": target.recipient_id,
                "message_id": message_id,
            },
        )
        return SendResult(
            accepted=True,
            external_message_id=message_id,
            metadata=metadata,
        )

    def _resolve_receive_id_type(
        self,
        target: MessageTarget,
        content: OutboundMessage,
    ) -> str:
        _ = target
        metadata_receive_id_type = content.metadata.get("receive_id_type")
        if isinstance(metadata_receive_id_type, str) and metadata_receive_id_type:
            return metadata_receive_id_type
        return self.settings.feishu_message_receive_id_type

    @staticmethod
    def _build_message_request(
        *,
        receive_id: str,
        receive_id_type: str,
        content: OutboundMessage,
    ) -> Any:
        lark: Any = import_module("lark_oapi")

        request_body = {
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": content.text}, ensure_ascii=False),
        }
        return (
            lark.BaseRequest.builder()
            .http_method(lark.HttpMethod.POST)
            .uri("/open-apis/im/v1/messages")
            .token_types({lark.AccessTokenType.TENANT})
            .queries([("receive_id_type", receive_id_type)])
            .body(request_body)
            .build()
        )

    @staticmethod
    def _build_client(settings: Settings) -> FeishuClientProtocol:
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            raise ValueError("飞书配置缺失：需要提供 FEISHU_APP_ID 和 FEISHU_APP_SECRET。")

        lark: Any = import_module("lark_oapi")

        return (
            lark.Client.builder()
            .app_id(settings.feishu_app_id)
            .app_secret(settings.feishu_app_secret)
            .build()
        )

    @staticmethod
    def _load_response_body(response: Any) -> JSONObject:
        raw = getattr(response, "raw", None)
        if raw is None:
            return {}

        content = getattr(raw, "content", None)
        if content is None:
            return {}

        if isinstance(content, bytes):
            return json.loads(content.decode("utf-8"))
        if isinstance(content, str):
            return json.loads(content)
        return {}

    @staticmethod
    def _extract_message_id(response_body: JSONObject) -> str | None:
        data = response_body.get("data")
        if not isinstance(data, dict):
            return None

        message_id = data.get("message_id")
        if isinstance(message_id, str):
            return message_id
        return None
