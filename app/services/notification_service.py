from cashews import cache

from app.channels import IMManager, IMMessage, IMSendResult, MessageType
from app.channels.runtime import send_text_to_user
from app.config import settings
from app.enums import IMProvider
from app.utils import logger

CACHE_PREFIX = "user_im_channel"
CACHE_TTL = 86400 * 30


class NotificationService:
    def __init__(self, manager: IMManager | None = None) -> None:
        self._manager = manager

    @property
    def manager(self) -> IMManager | None:
        if self._manager is None and settings.im_enabled:
            configs = settings.get_im_configs()
            if configs:
                self._manager = IMManager(configs)
        return self._manager

    @staticmethod
    def _user_channel_key(user_id: str) -> str:
        return f"{CACHE_PREFIX}:{user_id}"

    async def set_user_channel(self, user_id: str, provider: IMProvider) -> None:
        key = self._user_channel_key(user_id)
        await cache.set(key, provider.value, expire=CACHE_TTL)
        logger.info(f"Set user {user_id} channel to {provider.value}")

    async def get_user_channel(self, user_id: str) -> IMProvider | None:
        key = self._user_channel_key(user_id)
        value = await cache.get(key)
        if value:
            try:
                return IMProvider(value)
            except ValueError:
                pass
        return None

    @staticmethod
    async def _send_via_bot(
        provider: IMProvider, user_id: str, content: str
    ) -> IMSendResult | None:
        if provider not in (IMProvider.DISCORD, IMProvider.FEISHU):
            return None

        result = await send_text_to_user(provider, user_id, content)
        return IMSendResult(success=result.success, error=result.error)

    async def send(self, message: IMMessage, user_id: str | None = None) -> IMSendResult:
        providers = self.get_available_providers()
        if not providers:
            logger.warning("No IM providers available")
            return IMSendResult(success=False, error="No IM providers available")

        target_provider = None
        if user_id:
            target_provider = await self.get_user_channel(user_id)

        if not target_provider:
            target_provider = providers[0]

        if user_id and message.msg_type == MessageType.TEXT:
            bot_result = await self._send_via_bot(target_provider, user_id, message.content)
            if bot_result is not None:
                return bot_result

        if self.manager:
            config = settings.get_im_config(target_provider)
            if config and config.webhook_url:
                return await self.manager.send_to_provider(target_provider, message)

        logger.warning(f"No available channel for provider {target_provider.value}")
        return IMSendResult(
            success=False, error=f"No available channel for {target_provider.value}"
        )

    async def send_text(self, content: str, user_id: str | None = None) -> IMSendResult:
        message = IMMessage(content=content, msg_type=MessageType.TEXT)
        return await self.send(message, user_id)

    async def send_markdown(
        self, title: str, content: str, user_id: str | None = None
    ) -> IMSendResult:
        message = IMMessage(content=content, msg_type=MessageType.MARKDOWN, title=title)
        return await self.send(message, user_id)

    async def send_to_all(self, message: IMMessage) -> list[IMSendResult]:
        if not self.manager:
            logger.warning("IM not configured, skipping notification")
            return [IMSendResult(success=False, error="IM not configured")]

        return await self.manager.send_to_all(message)

    async def notify_capture_success(
        self, uuid: str, content: str, user_id: str | None = None
    ) -> IMSendResult:
        truncated = content[:100] + "..." if len(content) > 100 else content
        message = IMMessage(
            content=f"✅ Captured\n\nUUID: {uuid}\nContent: {truncated}",
            msg_type=MessageType.MARKDOWN,
        )
        return await self.send(message, user_id)

    async def notify_error(self, error_msg: str, user_id: str | None = None) -> IMSendResult:
        return await self.send_text(f"❌ Error: {error_msg}", user_id)

    @staticmethod
    def get_available_providers() -> list[IMProvider]:
        if not settings.im_enabled:
            return []
        return [cfg.provider for cfg in settings.get_im_configs() if cfg.enabled]
