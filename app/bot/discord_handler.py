import discord

from app.bot.message_service import BotMessageService, IncomingMessage
from app.utils.logging import logger

service = BotMessageService()


async def handle_discord_message(message: discord.Message) -> None:
    channel_id = message.channel.id if message.channel else None

    async def reply(content: str) -> None:
        await message.channel.send(content)

    incoming = IncomingMessage(
        provider="discord",
        user_id=str(message.author.id),
        text=message.content,
        reply=reply,
        channel_id=channel_id,
    )

    try:
        await service.handle(incoming)
    except Exception as e:
        logger.error(f"Failed to handle Discord message: {e}")
        await message.channel.send(f"处理消息失败: {e}")
