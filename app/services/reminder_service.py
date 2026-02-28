import re
from datetime import datetime, timedelta
from typing import Any, cast

from app.models import Reminder
from app.utils import logger


class ReminderService:
    @staticmethod
    def _clean_reminder_content(content: str) -> str:
        cleaned = content.strip()
        cleaned = re.sub(r"^(提醒我|提醒|记得|请提醒我)\s*", "", cleaned)
        return cleaned.strip()

    @staticmethod
    def _parse_cn_clock(
        now: datetime,
        day_hint: str | None,
        period_hint: str | None,
        hour_raw: int,
        minute_raw: int,
    ) -> datetime:
        hour = hour_raw
        minute = minute_raw
        period = (period_hint or "").strip()

        if period in ("下午", "晚上", "傍晚") and hour < 12:
            hour += 12
        if period in ("凌晨",) and hour == 12:
            hour = 0
        if period in ("中午",) and hour < 11:
            hour += 12

        if day_hint == "明天":
            base = now + timedelta(days=1)
        elif day_hint == "后天":
            base = now + timedelta(days=2)
        else:
            base = now

        remind_at = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if day_hint is None and remind_at <= now:
            remind_at += timedelta(days=1)
        return remind_at

    @staticmethod
    def parse_time_expression(text: str) -> tuple[datetime | None, str | None]:
        text = text.strip()
        now = datetime.now()

        # e.g. 下午5点提醒我出发 / 晚上10点 记得吃药 / 明天晚上8点开会
        cn_clock = re.search(
            r"(?:(今天|明天|后天)\s*)?(上午|中午|下午|晚上|凌晨|早上|傍晚)?\s*(\d{1,2})\s*点(?:\s*(\d{1,2})\s*分?)?",
            text,
        )
        if cn_clock:
            day_hint = cn_clock.group(1)
            period_hint = cn_clock.group(2)
            hour = int(cn_clock.group(3))
            minute = int(cn_clock.group(4) or 0)
            remind_at = ReminderService._parse_cn_clock(
                now=now,
                day_hint=day_hint,
                period_hint=period_hint,
                hour_raw=hour,
                minute_raw=minute,
            )
            content = (text[: cn_clock.start()] + " " + text[cn_clock.end() :]).strip()
            content = ReminderService._clean_reminder_content(content)
            return remind_at, content

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
                    content = ReminderService._clean_reminder_content(re.sub(pattern, "", text))
                    return remind_at, content

                elif time_type == "hours":
                    hours = int(match.group(1))
                    remind_at = now + timedelta(hours=hours)
                    content = ReminderService._clean_reminder_content(re.sub(pattern, "", text))
                    return remind_at, content

                elif time_type == "days":
                    days = int(match.group(1))
                    remind_at = now + timedelta(days=days)
                    content = ReminderService._clean_reminder_content(re.sub(pattern, "", text))
                    return remind_at, content

                elif time_type == "today_time":
                    hour = int(match.group(1))
                    minute = int(match.group(2))
                    remind_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if remind_at <= now:
                        remind_at += timedelta(days=1)
                    content = ReminderService._clean_reminder_content(re.sub(pattern, "", text))
                    return remind_at, content

                elif time_type == "tomorrow_time":
                    hour = int(match.group(1))
                    minute = int(match.group(2))
                    remind_at = (now + timedelta(days=1)).replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )
                    content = ReminderService._clean_reminder_content(re.sub(pattern, "", text))
                    return remind_at, content

                elif time_type == "tomorrow_morning":
                    remind_at = (now + timedelta(days=1)).replace(
                        hour=9, minute=0, second=0, microsecond=0
                    )
                    content = ReminderService._clean_reminder_content(re.sub(pattern, "", text))
                    return remind_at, content

                elif time_type == "tomorrow_afternoon":
                    remind_at = (now + timedelta(days=1)).replace(
                        hour=14, minute=0, second=0, microsecond=0
                    )
                    content = ReminderService._clean_reminder_content(re.sub(pattern, "", text))
                    return remind_at, content

                elif time_type == "before_work_end":
                    remind_at = now.replace(hour=18, minute=0, second=0, microsecond=0)
                    if remind_at <= now:
                        remind_at += timedelta(days=1)
                    content = ReminderService._clean_reminder_content(re.sub(pattern, "", text))
                    return remind_at, content

        return None, None

    @staticmethod
    def parse_delay_minutes(text: str) -> int | None:
        cleaned = text.strip()
        # e.g. "延迟15分钟提醒我", "这条通知延后 10 分钟", "顺延20分钟"
        match = re.search(r"(延迟|延后|顺延)\s*(\d{1,3})\s*分钟", cleaned)
        if match:
            return int(match.group(2))
        return None

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
        is_sent_col = cast(Any, Reminder.is_sent)
        remind_at_col = cast(Any, Reminder.remind_at)
        reminders = (
            await Reminder.select()
            .where(is_sent_col == False)  # noqa: E712
            .where(remind_at_col <= now)
            .order_by(remind_at_col)
        )
        return [Reminder(**r) for r in reminders]

    @staticmethod
    async def get_user_reminders(user_id: str, limit: int = 10) -> list[Reminder]:
        user_id_col = cast(Any, Reminder.user_id)
        is_sent_col = cast(Any, Reminder.is_sent)
        remind_at_col = cast(Any, Reminder.remind_at)
        reminders = (
            await Reminder.select()
            .where(user_id_col == user_id)
            .where(is_sent_col == False)  # noqa: E712
            .order_by(remind_at_col)
            .limit(limit)
        )
        return [Reminder(**r) for r in reminders]

    @staticmethod
    async def mark_as_sent(reminder_id: int) -> None:
        id_col = cast(Any, Reminder.id)
        await Reminder.update(is_sent=True, sent_at=datetime.now()).where(id_col == reminder_id)

    @staticmethod
    async def get_reminder_status(
        user_id: str,
        provider: str | None = None,
        channel_id: int | None = None,
        limit: int = 5,
    ) -> tuple[list[Reminder], list[Reminder]]:
        user_id_col = cast(Any, Reminder.user_id)
        provider_col = cast(Any, Reminder.provider)
        channel_id_col = cast(Any, Reminder.channel_id)
        is_sent_col = cast(Any, Reminder.is_sent)
        remind_at_col = cast(Any, Reminder.remind_at)
        sent_at_col = cast(Any, Reminder.sent_at)

        pending_query = Reminder.select().where(user_id_col == user_id).where(is_sent_col == False)  # noqa: E712
        sent_query = Reminder.select().where(user_id_col == user_id).where(is_sent_col == True)  # noqa: E712

        if provider:
            pending_query = pending_query.where(provider_col == provider)
            sent_query = sent_query.where(provider_col == provider)
        if channel_id is not None:
            pending_query = pending_query.where(channel_id_col == channel_id)
            sent_query = sent_query.where(channel_id_col == channel_id)

        pending_rows = await pending_query.order_by(remind_at_col).limit(limit)
        sent_rows = await sent_query.order_by(sent_at_col, ascending=False).limit(limit)
        pending = [Reminder(**row) for row in pending_rows]
        sent = [Reminder(**row) for row in sent_rows]
        return sent, pending

    @staticmethod
    async def delay_latest_reminder(
        user_id: str,
        delay_minutes: int,
        provider: str | None = None,
        channel_id: int | None = None,
    ) -> Reminder | None:
        user_id_col = cast(Any, Reminder.user_id)
        provider_col = cast(Any, Reminder.provider)
        channel_id_col = cast(Any, Reminder.channel_id)
        created_at_col = cast(Any, Reminder.created_at)
        id_col = cast(Any, Reminder.id)

        query = Reminder.select().where(user_id_col == user_id)
        if provider:
            query = query.where(provider_col == provider)
        if channel_id is not None:
            query = query.where(channel_id_col == channel_id)
        rows = await query.order_by(created_at_col, ascending=False).limit(1)
        if not rows:
            return None

        latest = Reminder(**rows[0])
        now = datetime.now()

        # If reminder hasn't triggered yet, postpone in place.
        if not latest.is_sent and latest.remind_at > now:
            new_time = latest.remind_at + timedelta(minutes=delay_minutes)
            await Reminder.update(
                remind_at=new_time,
                is_advance_sent=False,
            ).where(id_col == latest.id)
            latest.remind_at = new_time
            latest.is_advance_sent = False
            return latest

        # Otherwise create a new reminder from now with same content.
        new_time = now + timedelta(minutes=delay_minutes)
        reminder = Reminder(
            content=latest.content,
            remind_at=new_time,
            user_id=user_id,
            channel_id=channel_id if channel_id is not None else latest.channel_id,
            guild_id=latest.guild_id,
            is_sent=False,
            is_advance_sent=False,
            sent_at=None,
            provider=provider or latest.provider,
        )
        await reminder.save()

        # Optional: mark old as sent if it wasn't yet, to avoid duplicate fire.
        if not latest.is_sent:
            await Reminder.update(is_sent=True, sent_at=now).where(id_col == latest.id)

        return reminder

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
