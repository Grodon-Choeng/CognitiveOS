from app.channels.registry import CHANNEL_STARTERS, CHANNEL_STOPPERS
from app.config import settings
from app.services.notification_service import NotificationService
from app.services.reminder_checker import start_reminder_checker, stop_reminder_checker
from app.utils.logging import logger

from .discord_handler import handle_discord_message
from .feishu_handler import handle_feishu_message


async def _alert_ops(message: str) -> None:
    logger.error(f"[FeishuAlert] {message}")
    try:
        service = NotificationService()
        await service.send_text(f"[FeishuBot] {message}")
    except Exception as e:
        logger.error(f"Failed to send Feishu alert via NotificationService: {e}")


async def start_bot() -> None:
    if not settings.im_enabled:
        logger.info("IM disabled, skipping bot startup")
        return

    message_handlers = {
        "discord": handle_discord_message,
        "feishu": handle_feishu_message,
    }
    alert_handlers = {
        "feishu": _alert_ops,
    }

    enabled_providers = [cfg.provider.value for cfg in settings.get_im_configs() if cfg.enabled]

    for provider in enabled_providers:
        starter = CHANNEL_STARTERS.get(provider)
        if starter is None:
            logger.info(f"Provider {provider} has no long-connection starter, skipped")
            continue

        kwargs = {"on_message_callback": message_handlers.get(provider)}
        if provider in alert_handlers:
            kwargs["on_alert_callback"] = alert_handlers[provider]
        await starter(**kwargs)

    start_reminder_checker()


async def stop_bot() -> None:
    if not settings.im_enabled:
        return

    stop_reminder_checker()
    for stop in CHANNEL_STOPPERS.values():
        await stop()


__all__ = [
    "handle_discord_message",
    "handle_feishu_message",
    "start_bot",
    "stop_bot",
]
