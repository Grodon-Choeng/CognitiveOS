from app.bot.discord_handler import handle_discord_message
from app.bot.feishu_handler import handle_feishu_message
from app.config import settings
from app.services import (
    NotificationService,
    start_discord_bot,
    start_feishu_bot,
    stop_discord_bot,
    stop_feishu_bot,
)
from app.services.reminder_checker import start_reminder_checker, stop_reminder_checker
from app.utils.logging import logger


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

    enabled_providers = {cfg.provider.value for cfg in settings.get_im_configs()}

    if "discord" in enabled_providers:
        await start_discord_bot(on_message_callback=handle_discord_message)
    else:
        logger.info("Discord bot disabled by config")

    if "feishu" in enabled_providers:
        await start_feishu_bot(
            on_message_callback=handle_feishu_message,
            on_alert_callback=_alert_ops,
        )
    else:
        logger.info("Feishu bot disabled by config")

    start_reminder_checker()


async def stop_bot() -> None:
    if not settings.im_enabled:
        return

    stop_reminder_checker()
    await stop_discord_bot()
    await stop_feishu_bot()


__all__ = [
    "handle_discord_message",
    "handle_feishu_message",
    "start_bot",
    "stop_bot",
]
