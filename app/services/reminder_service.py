import re
from datetime import datetime, timedelta

from app.models import Reminder
from app.utils import logger


class ReminderService:
    @staticmethod
    def parse_time_expression(text: str) -> tuple[datetime | None, str | None]:
        text = text.strip()
        now = datetime.now()

        patterns = [
            (r"(\d+)\s*分钟后?", "minutes"),
            (r"(\d+)\s*小时后?", "hours"),
            (r"(\d+)\s*天后?", "days"),
            (r"今天\s*(\d{1,2}):(\d{1,2})", "today_time"),
            (r"明天\s*(\d{1,2}):(\d{1,2})", "tomorrow_time"),
            (r"明天早上", "tomorrow_morning"),
            (r"明天下午", "tomorrow_afternoon"),
            (r"今天下班前", "before_work_end"),
            (r"下班前", "before_work_end"),
        ]

        for pattern, time_type in patterns:
            match = re.search(pattern, text)
            if match:
                if time_type == "minutes":
                    minutes = int(match.group(1))
                    remind_at = now + timedelta(minutes=minutes)
                    content = re.sub(pattern, "", text).strip()
                    return remind_at, content

                elif time_type == "hours":
                    hours = int(match.group(1))
                    remind_at = now + timedelta(hours=hours)
                    content = re.sub(pattern, "", text).strip()
                    return remind_at, content

                elif time_type == "days":
                    days = int(match.group(1))
                    remind_at = now + timedelta(days=days)
                    content = re.sub(pattern, "", text).strip()
                    return remind_at, content

                elif time_type == "today_time":
                    hour = int(match.group(1))
                    minute = int(match.group(2))
                    remind_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if remind_at <= now:
                        remind_at += timedelta(days=1)
                    content = re.sub(pattern, "", text).strip()
                    return remind_at, content

                elif time_type == "tomorrow_time":
                    hour = int(match.group(1))
                    minute = int(match.group(2))
                    remind_at = (now + timedelta(days=1)).replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )
                    content = re.sub(pattern, "", text).strip()
                    return remind_at, content

                elif time_type == "tomorrow_morning":
                    remind_at = (now + timedelta(days=1)).replace(
                        hour=9, minute=0, second=0, microsecond=0
                    )
                    content = re.sub(pattern, "", text).strip()
                    return remind_at, content

                elif time_type == "tomorrow_afternoon":
                    remind_at = (now + timedelta(days=1)).replace(
                        hour=14, minute=0, second=0, microsecond=0
                    )
                    content = re.sub(pattern, "", text).strip()
                    return remind_at, content

                elif time_type == "before_work_end":
                    remind_at = now.replace(hour=18, minute=0, second=0, microsecond=0)
                    if remind_at <= now:
                        remind_at += timedelta(days=1)
                    content = re.sub(pattern, "", text).strip()
                    return remind_at, content

        return None, None

    @staticmethod
    async def create_reminder(
        content: str,
        remind_at: datetime,
        user_id: str,
        channel_id: int | None = None,
        guild_id: int | None = None,
        provider: str = "discord",
    ) -> Reminder:
        reminder = Reminder(
            content=content,
            remind_at=remind_at,
            user_id=user_id,
            channel_id=channel_id,
            guild_id=guild_id,
            is_sent=False,
            provider=provider,
        )
        await reminder.save()
        logger.info(f"Created reminder: {content} at {remind_at}")
        return reminder

    @staticmethod
    async def get_pending_reminders() -> list[Reminder]:
        now = datetime.now()
        reminders = (
            await Reminder.select()
            .where(Reminder.is_sent == False)  # noqa: E712
            .where(Reminder.remind_at <= now)
            .order_by(Reminder.remind_at)
        )
        return [Reminder(**r) for r in reminders]

    @staticmethod
    async def get_user_reminders(user_id: str, limit: int = 10) -> list[Reminder]:
        reminders = (
            await Reminder.select()
            .where(Reminder.user_id == user_id)
            .where(Reminder.is_sent == False)  # noqa: E712
            .order_by(Reminder.remind_at)
            .limit(limit)
        )
        return [Reminder(**r) for r in reminders]

    @staticmethod
    async def mark_as_sent(reminder_id: int) -> None:
        await Reminder.update(is_sent=True, sent_at=datetime.now()).where(
            Reminder.id == reminder_id
        )

    @staticmethod
    def format_time_remaining(remind_at: datetime) -> str:
        now = datetime.now()
        delta = remind_at - now

        if delta.total_seconds() < 0:
            return "已过期"

        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")

        return " ".join(parts) if parts else "即将"
