from app.bot.message_service import BotMessageService, IncomingMessage
from app.channels.feishu import FeishuIncomingMessage, get_feishu_bot
from app.utils.logging import logger

service = BotMessageService()


async def handle_feishu_message(message: FeishuIncomingMessage) -> None:
    async def reply(content: str) -> None:
        bot = get_feishu_bot()
        if not bot:
            logger.warning("Feishu bot not available while replying")
            return

        sent = await bot.send_text_to_chat(message.chat_id, content)
        if not sent:
            await bot.send_text_to_user(message.user_open_id, content)

    incoming = IncomingMessage(
        provider="feishu",
        user_id=message.user_open_id,
        text=message.text,
        reply=reply,
    )

    try:
        await service.handle(incoming)
    except Exception as e:
        logger.error(f"Failed to handle Feishu message: {e}")
        await reply(f"处理消息失败: {e}")
