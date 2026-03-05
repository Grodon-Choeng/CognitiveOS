import re
from datetime import datetime, timedelta
from typing import Any, Literal, cast

from app.models import Reminder
from app.services.calendar_service import ChinaWorkdayCalendarService
from app.utils import logger


class ReminderService:
    _calendar = ChinaWorkdayCalendarService()

    @staticmethod
    def _apply_recurrence_wording(content: str, rule: str | None) -> str:
        cleaned = content.strip()
        if not cleaned:
            return cleaned
        if rule == "WEEKDAYS":
            cleaned = re.sub(r"^每天", "工作日", cleaned)
            cleaned = re.sub(r"^每日", "工作日", cleaned)
        elif rule == "DAILY":
            cleaned = re.sub(r"^工作日", "每天", cleaned)
        return cleaned

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
    def parse_snooze_delta(text: str) -> timedelta | None:
        cleaned = text.strip()
        match = re.search(r"(延迟|延后|顺延)\s*(\d{1,3})\s*(分钟|小时|天)", cleaned)
        if not match:
            return None
        value = int(match.group(2))
        unit = match.group(3)
        if unit == "分钟":
            return timedelta(minutes=value)
        if unit == "小时":
            return timedelta(hours=value)
        if unit == "天":
            return timedelta(days=value)
        return None

    @staticmethod
    def parse_recurrence_rule(text: str) -> Literal["NONE", "DAILY", "WEEKDAYS"] | None:
        cleaned = text.strip()
        if any(
            token in cleaned for token in ("仅有明天", "仅明天", "只明天", "就明天", "只提醒一次")
        ):
            return "NONE"
        if any(token in cleaned for token in ("工作日", "周一到周五")):
            return "WEEKDAYS"
        if any(token in cleaned for token in ("每天", "每日", "天天")):
            return "DAILY"
        return None

    @staticmethod
    def _normalize_content_for_recurrence(content: str) -> str:
        cleaned = content
        cleaned = re.sub(
            r"(每天|每日|天天|工作日|周一到周五|仅有明天|仅明天|只明天|就明天|只提醒一次)",
            " ",
            cleaned,
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,。！!？?")
        return cleaned.strip()

    @staticmethod
    def next_occurrence(base: datetime, rule: str, now: datetime | None = None) -> datetime:
        now_time = now or datetime.now()
        candidate = base
        while candidate <= now_time:
            candidate = candidate + timedelta(days=1)
        if rule == "WEEKDAYS":
            candidate = ReminderService._calendar.next_workday_datetime(candidate)
        return candidate

    @staticmethod
    async def create_reminder(
        content: str,
        remind_at: datetime,
        user_id: str,
        channel_id: int | None = None,
        guild_id: int | None = None,
        provider: str = "discord",
        recurrence_rule: str | None = None,
        advance_minutes: int = 1,
        retry_interval_minutes: int = 0,
        max_retries: int = 0,
        require_ack: bool = False,
        calendar_type: str | None = None,
    ) -> Reminder:
        normalized_rule = (recurrence_rule or "").strip().upper() or None
        is_recurring = normalized_rule in {"DAILY", "WEEKDAYS"}
        normalized_content = ReminderService._normalize_content_for_recurrence(content)
        normalized_calendar = (calendar_type or "").strip().lower() or (
            "cn_workday" if normalized_rule == "WEEKDAYS" else "gregorian"
        )
        final_content = ReminderService._apply_recurrence_wording(
            normalized_content or content,
            normalized_rule,
        )
        reminder = Reminder(
            content=final_content,
            remind_at=remind_at,
            user_id=user_id,
            channel_id=channel_id,
            guild_id=guild_id,
            is_sent=False,
            provider=provider,
            is_recurring=is_recurring,
            recurrence_rule=normalized_rule,
            plan_type="recurring" if is_recurring else "one_time",
            calendar_type=normalized_calendar,
            advance_minutes=max(0, int(advance_minutes)),
            retry_interval_minutes=max(0, int(retry_interval_minutes)),
            max_retries=max(0, int(max_retries)),
            retry_count=0,
            require_ack=require_ack,
            status="active",
        )
        await reminder.save()
        logger.info(
            f"Created reminder: {reminder.content} at {remind_at}, recurring={is_recurring}, rule={normalized_rule}"
        )
        return reminder

    @staticmethod
    async def get_pending_reminders() -> list[Reminder]:
        now = datetime.now()
        is_sent_col = cast(Any, Reminder.is_sent)
        remind_at_col = cast(Any, Reminder.remind_at)
        status_col = cast(Any, Reminder.status)
        pause_until_col = cast(Any, Reminder.pause_until)
        reminders = (
            await Reminder.select()
            .where(is_sent_col == False)  # noqa: E712
            .where(status_col == "active")
            .where(remind_at_col <= now)
            .where((pause_until_col == None) | (pause_until_col <= now))  # noqa: E711
            .order_by(remind_at_col)
        )
        return [Reminder(**r) for r in reminders]

    @staticmethod
    async def get_user_reminders(user_id: str, limit: int = 10) -> list[Reminder]:
        user_id_col = cast(Any, Reminder.user_id)
        is_sent_col = cast(Any, Reminder.is_sent)
        remind_at_col = cast(Any, Reminder.remind_at)
        now = datetime.now()
        reminders = (
            await Reminder.select()
            .where(user_id_col == user_id)
            .where(is_sent_col == False)  # noqa: E712
            .where(remind_at_col >= now - timedelta(days=1))
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
        sent_lookback_days: int = 7,
    ) -> tuple[list[Reminder], list[Reminder]]:
        user_id_col = cast(Any, Reminder.user_id)
        provider_col = cast(Any, Reminder.provider)
        channel_id_col = cast(Any, Reminder.channel_id)
        is_sent_col = cast(Any, Reminder.is_sent)
        remind_at_col = cast(Any, Reminder.remind_at)
        sent_at_col = cast(Any, Reminder.sent_at)
        now = datetime.now()
        sent_since = now - timedelta(days=max(1, sent_lookback_days))

        pending_query = (
            Reminder.select()
            .where(user_id_col == user_id)
            .where(is_sent_col == False)  # noqa: E712
            .where(remind_at_col >= now - timedelta(days=1))
        )
        sent_query = (
            Reminder.select().where(user_id_col == user_id).where(sent_at_col >= sent_since)
        )

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
    async def update_latest_reminder_recurrence(
        user_id: str,
        recurrence_rule: str,
        provider: str | None = None,
        channel_id: int | None = None,
        target_reminder_id: int | None = None,
    ) -> Reminder | None:
        normalized_rule = recurrence_rule.strip().upper()
        if normalized_rule not in {"NONE", "DAILY", "WEEKDAYS"}:
            return None

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
        if target_reminder_id is not None:
            query = query.where(id_col == target_reminder_id)

        rows = await query.order_by(created_at_col, ascending=False).limit(1)
        if not rows:
            return None

        reminder = Reminder(**rows[0])
        now = datetime.now()
        is_recurring = normalized_rule in {"DAILY", "WEEKDAYS"}
        next_time = reminder.remind_at
        if is_recurring:
            next_time = ReminderService.next_occurrence(
                base=reminder.remind_at,
                rule=normalized_rule,
                now=now,
            )
        elif next_time <= now:
            # keep one-shot but ensure it's still actionable for follow-up edits
            next_time = now + timedelta(minutes=1)

        updated_content = ReminderService._apply_recurrence_wording(
            reminder.content, normalized_rule
        )
        await Reminder.update(
            content=updated_content,
            plan_type="recurring" if is_recurring else "one_time",
            calendar_type="cn_workday" if normalized_rule == "WEEKDAYS" else "gregorian",
            is_recurring=is_recurring,
            recurrence_rule=None if normalized_rule == "NONE" else normalized_rule,
            remind_at=next_time,
            is_sent=False,
            is_advance_sent=False,
        ).where(id_col == reminder.id)
        reminder.content = updated_content
        reminder.is_recurring = is_recurring
        reminder.recurrence_rule = None if normalized_rule == "NONE" else normalized_rule
        reminder.plan_type = "recurring" if is_recurring else "one_time"
        reminder.calendar_type = "cn_workday" if normalized_rule == "WEEKDAYS" else "gregorian"
        reminder.remind_at = next_time
        reminder.is_sent = False
        reminder.is_advance_sent = False
        return reminder

    @staticmethod
    async def get_workday_reminders(
        user_id: str,
        provider: str | None = None,
        channel_id: int | None = None,
        include_sent: bool = False,
        limit: int = 10,
    ) -> tuple[list[Reminder], list[Reminder]]:
        user_id_col = cast(Any, Reminder.user_id)
        provider_col = cast(Any, Reminder.provider)
        channel_id_col = cast(Any, Reminder.channel_id)
        is_sent_col = cast(Any, Reminder.is_sent)
        remind_at_col = cast(Any, Reminder.remind_at)
        recurrence_rule_col = cast(Any, Reminder.recurrence_rule)
        sent_at_col = cast(Any, Reminder.sent_at)
        now = datetime.now()

        pending_query = (
            Reminder.select()
            .where(user_id_col == user_id)
            .where(is_sent_col == False)  # noqa: E712
            .where(recurrence_rule_col == "WEEKDAYS")
            .where(remind_at_col >= now - timedelta(days=1))
        )
        sent_query = (
            Reminder.select()
            .where(user_id_col == user_id)
            .where(recurrence_rule_col == "WEEKDAYS")
            .where(sent_at_col >= now - timedelta(days=7))
        )

        if provider:
            pending_query = pending_query.where(provider_col == provider)
            sent_query = sent_query.where(provider_col == provider)
        if channel_id is not None:
            pending_query = pending_query.where(channel_id_col == channel_id)
            sent_query = sent_query.where(channel_id_col == channel_id)

        pending_rows = await pending_query.order_by(remind_at_col).limit(limit)
        pending = [Reminder(**row) for row in pending_rows]
        if not include_sent:
            return [], pending
        sent_rows = await sent_query.order_by(sent_at_col, ascending=False).limit(limit)
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
    async def get_latest_reminder(
        user_id: str,
        provider: str | None = None,
        channel_id: int | None = None,
        target_reminder_id: int | None = None,
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
        if target_reminder_id is not None:
            query = query.where(id_col == target_reminder_id)
        rows = await query.order_by(created_at_col, ascending=False).limit(1)
        if not rows:
            return None
        return Reminder(**rows[0])

    @staticmethod
    async def snooze_latest_reminder(
        user_id: str,
        delta: timedelta,
        provider: str | None = None,
        channel_id: int | None = None,
        target_reminder_id: int | None = None,
    ) -> Reminder | None:
        reminder = await ReminderService.get_latest_reminder(
            user_id=user_id,
            provider=provider,
            channel_id=channel_id,
            target_reminder_id=target_reminder_id,
        )
        if reminder is None:
            return None
        id_col = cast(Any, Reminder.id)
        new_time = max(reminder.remind_at, datetime.now()) + delta
        await Reminder.update(
            remind_at=new_time,
            is_sent=False,
            is_advance_sent=False,
            retry_count=0,
            pause_until=None,
            status="active",
        ).where(id_col == reminder.id)
        reminder.remind_at = new_time
        reminder.is_sent = False
        reminder.is_advance_sent = False
        reminder.retry_count = 0
        reminder.pause_until = None
        reminder.status = "active"
        return reminder

    @staticmethod
    async def pause_latest_reminder_until(
        user_id: str,
        pause_until: datetime,
        provider: str | None = None,
        channel_id: int | None = None,
        target_reminder_id: int | None = None,
    ) -> Reminder | None:
        reminder = await ReminderService.get_latest_reminder(
            user_id=user_id,
            provider=provider,
            channel_id=channel_id,
            target_reminder_id=target_reminder_id,
        )
        if reminder is None:
            return None
        id_col = cast(Any, Reminder.id)
        await Reminder.update(
            pause_until=pause_until,
            status="paused" if pause_until > datetime.now() else "active",
            is_advance_sent=False,
        ).where(id_col == reminder.id)
        reminder.pause_until = pause_until
        reminder.status = "paused" if pause_until > datetime.now() else "active"
        reminder.is_advance_sent = False
        return reminder

    @staticmethod
    async def skip_next_occurrence(
        user_id: str,
        provider: str | None = None,
        channel_id: int | None = None,
        target_reminder_id: int | None = None,
    ) -> Reminder | None:
        reminder = await ReminderService.get_latest_reminder(
            user_id=user_id,
            provider=provider,
            channel_id=channel_id,
            target_reminder_id=target_reminder_id,
        )
        if reminder is None:
            return None
        next_time = reminder.remind_at
        rule = (reminder.recurrence_rule or "").upper()
        if rule in {"DAILY", "WEEKDAYS"}:
            next_time = ReminderService.next_occurrence(
                base=reminder.remind_at + timedelta(minutes=1),
                rule=rule,
                now=reminder.remind_at,
            )
        else:
            next_time = reminder.remind_at + timedelta(days=1)
        id_col = cast(Any, Reminder.id)
        await Reminder.update(
            remind_at=next_time,
            is_sent=False,
            is_advance_sent=False,
            retry_count=0,
            status="active",
        ).where(id_col == reminder.id)
        reminder.remind_at = next_time
        reminder.is_sent = False
        reminder.is_advance_sent = False
        reminder.retry_count = 0
        reminder.status = "active"
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
