from app.bot.message_service import BotMessageService, IncomingMessage
from app.channels.discord import start_discord_bot, stop_discord_bot
from app.services.reminder_checker import start_reminder_checker, stop_reminder_checker
from app.utils.logging import logger

service = BotMessageService()


async def handle_discord_message(message) -> None:
    async def reply(content: str) -> None:
        await message.channel.send(content)

    incoming = IncomingMessage(
        provider="discord",
        user_id=str(message.author.id),
        text=message.content,
        reply=reply,
        channel_id=message.channel.id if message.channel else None,
    )

    try:
        await service.handle(incoming)
    except Exception as e:
        logger.error(f"Failed to handle Discord message: {e}")
        await reply(f"处理消息失败: {e}")


def handle_discord_alert(message: str) -> None:
    logger.error(f"[Discord Alert] {message}")


async def start_bot() -> None:
    await start_discord_bot(
        on_message_callback=handle_discord_message,
        on_alert_callback=handle_discord_alert,
    )
    start_reminder_checker()


async def stop_bot() -> None:
    stop_reminder_checker()
    await stop_discord_bot()
