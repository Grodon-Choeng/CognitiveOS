from abc import ABC, abstractmethod
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


class IMAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def send(self, message: IMMessage) -> IMSendResult:
        pass

    @abstractmethod
    async def send_text(self, content: str) -> IMSendResult:
        pass

    @abstractmethod
    async def send_markdown(self, title: str, content: str) -> IMSendResult:
        pass

    async def health_check(self) -> bool:
        try:
            result = await self.send_text("Health check")
            return result.success
        except Exception:
            return False
