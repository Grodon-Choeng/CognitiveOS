from dataclasses import dataclass, field
from typing import Protocol

from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class MessageTarget:
    channel: str
    recipient_id: str


@dataclass(slots=True, frozen=True)
class OutboundMessage:
    text: str
    metadata: JSONObject = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class SendResult:
    accepted: bool
    external_message_id: str | None = None
    metadata: JSONObject = field(default_factory=dict)


class MessagingAdapter(Protocol):
    async def send_message(
        self,
        target: MessageTarget,
        content: OutboundMessage,
    ) -> SendResult: ...


class NoopMessagingAdapter:
    async def send_message(
        self,
        target: MessageTarget,
        content: OutboundMessage,
    ) -> SendResult:
        _ = (target, content)
        raise NotImplementedError("消息发送适配器尚未接入具体 IM 渠道。")
