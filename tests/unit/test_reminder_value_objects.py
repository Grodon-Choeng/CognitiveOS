from datetime import UTC, datetime

import pytest

from app.domain.reminders.value_objects import ReminderSchedule


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
