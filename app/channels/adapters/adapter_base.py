from abc import ABC, abstractmethod

from app.channels.message import IMMessage, IMSendResult


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
