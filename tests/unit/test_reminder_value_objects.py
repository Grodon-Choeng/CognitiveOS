from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.reminders.value_objects import (
    ReminderRecurrence,
    ReminderSchedule,
    next_remind_at_for_recurrence,
)


def test_reminder_schedule_requires_timezone_aware_datetime() -> None:
    with pytest.raises(ValueError):
        ReminderSchedule(
            remind_at=datetime(2026, 3, 20, 9, 0),
            timezone="Asia/Shanghai",
        )


def test_reminder_schedule_requires_non_empty_timezone() -> None:
    with pytest.raises(ValueError):
        ReminderSchedule(
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="   ",
        )


def test_reminder_recurrence_requires_supported_weekday() -> None:
    with pytest.raises(ValueError):
        ReminderRecurrence(
            recurrence_type="weekly_by_weekdays",
            weekdays=("workday",),
            hour=9,
            minute=55,
        )


def test_next_remind_at_for_workdays_returns_same_day_future_slot() -> None:
    recurrence = ReminderRecurrence(
        recurrence_type="weekly_by_weekdays",
        weekdays=("mon", "tue", "wed", "thu", "fri"),
        hour=9,
        minute=55,
    )

    next_run = next_remind_at_for_recurrence(
        recurrence,
        timezone="Asia/Shanghai",
        after=datetime(2026, 3, 25, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )

    assert next_run.isoformat() == "2026-03-25T09:55:00+08:00"
