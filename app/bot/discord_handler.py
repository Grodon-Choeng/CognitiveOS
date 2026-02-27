from app.utils import logger

from .message_service import BotMessageService, IncomingMessage


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
        service = BotMessageService()
        await service.handle(incoming)
    except Exception as e:
        logger.error(f"Failed to handle Discord message: {e}")
        await reply(f"处理消息失败: {e}")
