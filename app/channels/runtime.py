from dataclasses import dataclass

from app.channels.discord import get_discord_bot
from app.channels.feishu import get_feishu_bot
from app.config import settings
from app.enums import IMProvider
from app.models import Reminder
from app.utils.logging import logger


@dataclass
class ChannelSendResult:
    success: bool
    error: str | None = None


def get_default_provider() -> IMProvider:
    configs = settings.get_im_configs()
    if configs:
        return configs[0].provider
    return IMProvider.DISCORD


async def send_text_to_user(provider: IMProvider, user_id: str, content: str) -> ChannelSendResult:
    if provider == IMProvider.DISCORD:
        bot = get_discord_bot()
        if not bot or not bot._connected:
            return ChannelSendResult(False, "Discord bot unavailable")
        try:
            success = await bot.send_to_user(int(user_id), content)
            return ChannelSendResult(success, None if success else "User not found")
        except Exception as e:
            logger.error(f"Failed to send via Discord bot: {e}")
            return ChannelSendResult(False, str(e))

    if provider == IMProvider.FEISHU:
        bot = get_feishu_bot()
        if not bot or not bot._connected:
            return ChannelSendResult(False, "Feishu bot unavailable")
        try:
            success = await bot.send_text_to_user_or_chat(user_id, content)
            return ChannelSendResult(success, None if success else "Send failed")
        except Exception as e:
            logger.error(f"Failed to send via Feishu bot: {e}")
            return ChannelSendResult(False, str(e))

    return ChannelSendResult(
        False, f"Provider {provider.value} is not supported by channel runtime"
    )


async def send_reminder(reminder: Reminder, is_advance: bool = False) -> bool:
    provider_raw = (reminder.provider or get_default_provider().value).lower()
    try:
        provider = IMProvider(provider_raw)
    except ValueError:
        provider = get_default_provider()

    if provider == IMProvider.FEISHU:
        bot = get_feishu_bot()
        if not bot:
            logger.warning("Feishu bot not available")
            return False

        prefix = "⏰ 即将提醒(1分钟后)" if is_advance else "⏰ 提醒"
        content = f"{prefix}: {reminder.content}"
        try:
            return await bot.send_text_to_user_or_chat(reminder.user_id, content)
        except Exception as e:
            logger.error(f"Failed to send Feishu reminder {reminder.id}: {e}")
            return False

    bot = get_discord_bot()
    if not bot:
        logger.warning("Discord bot not available")
        return False

    prefix = "⏰ **即将提醒** (1分钟后)" if is_advance else "⏰ **提醒**"

    try:
        if reminder.channel_id:
            channel = bot.bot.get_channel(reminder.channel_id)
            if channel:
                await channel.send(f"{prefix}: {reminder.content}")
                return True

            try:
                channel = await bot.bot.fetch_channel(reminder.channel_id)
                if channel:
                    await channel.send(f"{prefix}: {reminder.content}")
                    return True
            except Exception:
                pass

        user = bot.bot.get_user(int(reminder.user_id))
        if not user:
            user = await bot.bot.fetch_user(int(reminder.user_id))

        if user:
            await user.send(f"{prefix}: {reminder.content}")
            return True

        logger.warning(f"Cannot find channel or user for reminder {reminder.id}")
        return False

    except Exception as e:
        logger.error(f"Failed to send reminder {reminder.id}: {e}")
        return False
