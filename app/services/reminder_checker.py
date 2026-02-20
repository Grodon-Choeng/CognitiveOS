import asyncio
from datetime import datetime, timedelta

from app.models import Reminder
from app.services import get_discord_bot, get_feishu_bot
from app.utils.logging import logger


async def send_discord_reminder(bot, reminder: Reminder, is_advance: bool = False) -> bool:
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


async def send_feishu_reminder(bot, reminder: Reminder, is_advance: bool = False) -> bool:
    prefix = "⏰ 即将提醒(1分钟后)" if is_advance else "⏰ 提醒"
    content = f"{prefix}: {reminder.content}"
    try:
        return await bot.send_text_to_user_or_chat(reminder.user_id, content)
    except Exception as e:
        logger.error(f"Failed to send Feishu reminder {reminder.id}: {e}")
        return False


async def send_reminder(reminder: Reminder, is_advance: bool = False) -> bool:
    provider = (reminder.provider or "discord").lower()

    if provider == "feishu":
        bot = get_feishu_bot()
        if not bot:
            logger.warning("Feishu bot not available")
            return False
        return await send_feishu_reminder(bot, reminder, is_advance)

    bot = get_discord_bot()
    if not bot:
        logger.warning("Discord bot not available")
        return False
    return await send_discord_reminder(bot, reminder, is_advance)


def parse_reminder_from_row(row: dict) -> Reminder:
    reminder = Reminder()
    reminder.id = row.get("id")
    reminder.content = row.get("content")
    reminder.user_id = row.get("user_id")
    reminder.channel_id = row.get("channel_id")
    reminder.guild_id = row.get("guild_id")
    reminder.is_sent = row.get("is_sent", False)
    reminder.is_advance_sent = row.get("is_advance_sent", False)
    reminder.provider = row.get("provider", "discord")

    remind_at = row.get("remind_at")
    if isinstance(remind_at, str):
        reminder.remind_at = datetime.fromisoformat(remind_at.replace("Z", "+00:00"))
    elif isinstance(remind_at, datetime):
        reminder.remind_at = remind_at
    else:
        reminder.remind_at = datetime.now()

    sent_at = row.get("sent_at")
    if sent_at:
        if isinstance(sent_at, str):
            reminder.sent_at = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
        elif isinstance(sent_at, datetime):
            reminder.sent_at = sent_at

    return reminder


async def check_reminders() -> None:
    while True:
        try:
            now = datetime.now()
            advance_time = now + timedelta(minutes=1)

            rows = (
                await Reminder.select()
                .where(Reminder.is_sent == False)  # noqa: E712
                .where(Reminder.remind_at <= advance_time)
                .order_by(Reminder.remind_at)
            )

            for row in rows:
                try:
                    reminder = parse_reminder_from_row(row)

                    if reminder.remind_at <= now:
                        success = await send_reminder(reminder, is_advance=False)
                        if success:
                            await Reminder.update(is_sent=True, sent_at=datetime.now()).where(
                                Reminder.id == reminder.id
                            )
                            logger.info(f"Sent reminder: {reminder.content}")

                    elif reminder.remind_at <= advance_time and not reminder.is_advance_sent:
                        success = await send_reminder(reminder, is_advance=True)
                        if success:
                            await Reminder.update(is_advance_sent=True).where(
                                Reminder.id == reminder.id
                            )
                            logger.info(f"Sent advance reminder: {reminder.content}")

                except Exception as e:
                    logger.error(f"Error processing reminder row: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error checking reminders: {e}")

        await asyncio.sleep(30)


_reminder_task: asyncio.Task | None = None


def start_reminder_checker() -> None:
    global _reminder_task
    if _reminder_task is None or _reminder_task.done():
        _reminder_task = asyncio.create_task(check_reminders())
        logger.info("Reminder checker started")


def stop_reminder_checker() -> None:
    global _reminder_task
    if _reminder_task and not _reminder_task.done():
        _reminder_task.cancel()
        logger.info("Reminder checker stopped")
