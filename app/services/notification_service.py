from typing import TYPE_CHECKING

from app.config import settings
from app.im import IMAdapter, IMMessage, IMSendResult, MessageType, create_adapter
from app.utils.logging import logger

if TYPE_CHECKING:
    pass


class NotificationService:
    def __init__(self, adapter: IMAdapter | None = None) -> None:
        self._adapter = adapter

    @property
    def adapter(self) -> IMAdapter | None:
        if self._adapter is None and settings.im_enabled and settings.im_webhook_url:
            self._adapter = create_adapter(
                provider=settings.im_provider,
                webhook_url=settings.im_webhook_url,
            )
        return self._adapter

    async def send(self, message: IMMessage) -> IMSendResult:
        if not self.adapter:
            logger.warning("IM not configured, skipping notification")
            return IMSendResult(success=False, error="IM not configured")

        return await self.adapter.send(message)

    async def send_text(self, content: str) -> IMSendResult:
        if not self.adapter:
            logger.warning("IM not configured, skipping notification")
            return IMSendResult(success=False, error="IM not configured")

        return await self.adapter.send_text(content)

    async def send_markdown(self, title: str, content: str) -> IMSendResult:
        if not self.adapter:
            logger.warning("IM not configured, skipping notification")
            return IMSendResult(success=False, error="IM not configured")

        return await self.adapter.send_markdown(title, content)

    async def notify_capture_success(self, uuid: str, content: str) -> IMSendResult:
        truncated = content[:100] + "..." if len(content) > 100 else content
        message = IMMessage(
            content=f"✅ Captured\n\nUUID: {uuid}\nContent: {truncated}",
            msg_type=MessageType.MARKDOWN,
        )
        return await self.send(message)

    async def notify_error(self, error_msg: str) -> IMSendResult:
        return await self.send_text(f"❌ Error: {error_msg}")
