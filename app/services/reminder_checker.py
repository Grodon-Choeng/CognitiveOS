import asyncio
from datetime import datetime, timedelta
from typing import Any, cast

from app.channels.runtime import get_default_provider, send_reminder
from app.models import Reminder
from app.utils import logger


def parse_reminder_from_row(row: dict) -> Reminder:
    reminder = Reminder()
    reminder.id = row.get("id")
    reminder.content = row.get("content")
    reminder.user_id = row.get("user_id")
    reminder.channel_id = row.get("channel_id")
    reminder.guild_id = row.get("guild_id")
    reminder.is_sent = row.get("is_sent", False)
    reminder.is_advance_sent = row.get("is_advance_sent", False)
    reminder.provider = row.get("provider", get_default_provider().value)

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

            is_sent_col = cast(Any, Reminder.is_sent)
            remind_at_col = cast(Any, Reminder.remind_at)
            id_col = cast(Any, Reminder.id)
            rows = (
                await Reminder.select()
                .where(is_sent_col == False)  # noqa: E712
                .where(remind_at_col <= advance_time)
                .order_by(remind_at_col)
            )

            for row in rows:
                try:
                    reminder = parse_reminder_from_row(row)

                    if reminder.remind_at <= now:
                        success = await send_reminder(reminder, is_advance=False)
                        if success:
                            await Reminder.update(is_sent=True, sent_at=datetime.now()).where(
                                id_col == reminder.id
                            )
                            logger.info(f"Sent reminder: {reminder.content}")

                    elif reminder.remind_at <= advance_time and not reminder.is_advance_sent:
                        success = await send_reminder(reminder, is_advance=True)
                        if success:
                            await Reminder.update(is_advance_sent=True).where(id_col == reminder.id)
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
