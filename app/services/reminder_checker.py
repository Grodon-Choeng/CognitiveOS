import asyncio
from datetime import datetime, timedelta
from typing import Any, cast

from app.channels.runtime import get_default_provider, send_reminder
from app.models import Reminder
from app.services.reminder_service import ReminderService
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
    reminder.is_recurring = row.get("is_recurring", False)
    reminder.recurrence_rule = row.get("recurrence_rule")
    reminder.advance_minutes = row.get("advance_minutes", 1)
    reminder.retry_interval_minutes = row.get("retry_interval_minutes", 0)
    reminder.max_retries = row.get("max_retries", 0)
    reminder.retry_count = row.get("retry_count", 0)
    reminder.require_ack = row.get("require_ack", False)
    reminder.pause_until = row.get("pause_until")
    reminder.status = row.get("status", "active")

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

    pause_until = row.get("pause_until")
    if pause_until:
        if isinstance(pause_until, str):
            reminder.pause_until = datetime.fromisoformat(pause_until.replace("Z", "+00:00"))
        elif isinstance(pause_until, datetime):
            reminder.pause_until = pause_until

    return reminder


async def check_reminders() -> None:
    while True:
        try:
            now = datetime.now()

            is_sent_col = cast(Any, Reminder.is_sent)
            remind_at_col = cast(Any, Reminder.remind_at)
            status_col = cast(Any, Reminder.status)
            pause_until_col = cast(Any, Reminder.pause_until)
            id_col = cast(Any, Reminder.id)
            rows = (
                await Reminder.select()
                .where(is_sent_col == False)  # noqa: E712
                .where(
                    (status_col == "active") | ((status_col == "paused") & (pause_until_col <= now))
                )
                .where(remind_at_col <= now + timedelta(days=1))
                .order_by(remind_at_col)
            )

            for row in rows:
                try:
                    reminder = parse_reminder_from_row(row)
                    if (
                        reminder.status == "paused"
                        and reminder.pause_until
                        and reminder.pause_until <= now
                    ):
                        await Reminder.update(status="active").where(id_col == reminder.id)
                        reminder.status = "active"

                    if reminder.status != "active":
                        continue

                    advance_window = now + timedelta(
                        minutes=max(0, int(reminder.advance_minutes or 0))
                    )

                    if reminder.remind_at <= now:
                        success = await send_reminder(reminder, is_advance=False)
                        if success:
                            if reminder.is_recurring and reminder.recurrence_rule:
                                next_time = ReminderService.next_occurrence(
                                    base=reminder.remind_at,
                                    rule=reminder.recurrence_rule,
                                    now=now,
                                )
                                await Reminder.update(
                                    remind_at=next_time,
                                    is_sent=False,
                                    is_advance_sent=False,
                                    retry_count=0,
                                    sent_at=datetime.now(),
                                    last_triggered_at=datetime.now(),
                                    status="active",
                                ).where(id_col == reminder.id)
                                logger.info(
                                    f"Sent recurring reminder: {reminder.content}, next at {next_time}"
                                )
                            elif int(reminder.retry_interval_minutes or 0) > 0 and int(
                                reminder.retry_count or 0
                            ) < int(reminder.max_retries or 0):
                                retry_time = now + timedelta(
                                    minutes=int(reminder.retry_interval_minutes or 0)
                                )
                                await Reminder.update(
                                    remind_at=retry_time,
                                    is_sent=False,
                                    is_advance_sent=False,
                                    retry_count=int(reminder.retry_count or 0) + 1,
                                    sent_at=datetime.now(),
                                    last_triggered_at=datetime.now(),
                                ).where(id_col == reminder.id)
                                logger.info(
                                    f"Sent reminder with retry schedule: {reminder.content}, retry at {retry_time}"
                                )
                            else:
                                await Reminder.update(
                                    is_sent=True,
                                    sent_at=datetime.now(),
                                    last_triggered_at=datetime.now(),
                                ).where(id_col == reminder.id)
                                logger.info(f"Sent reminder: {reminder.content}")

                    elif (
                        int(reminder.advance_minutes or 0) > 0
                        and reminder.remind_at <= advance_window
                        and not reminder.is_advance_sent
                    ):
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
