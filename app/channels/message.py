from dataclasses import dataclass
from enum import Enum
from typing import Any


class MessageType(str, Enum):
    TEXT = "text"
    MARKDOWN = "markdown"
    CARD = "card"


@dataclass
class IMMessage:
    content: str
    msg_type: MessageType = MessageType.TEXT
    title: str | None = None
    extra: dict[str, Any] | None = None


@dataclass
class IMSendResult:
    success: bool
    message_id: str | None = None
    error: str | None = None
