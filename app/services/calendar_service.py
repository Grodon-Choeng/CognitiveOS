from __future__ import annotations

from datetime import date, datetime, timedelta

from app.config import settings


class ChinaWorkdayCalendarService:
    def __init__(self) -> None:
        self._holiday_overrides = {d for d in settings.cn_holidays if d}
        self._workday_overrides = {d for d in settings.cn_makeup_workdays if d}
        try:
            import chinese_calendar as cn_calendar  # type: ignore

            self._calendar = cn_calendar
        except ModuleNotFoundError:
            self._calendar = None

    @staticmethod
    def _fmt_day(day: date) -> str:
        return day.strftime("%Y-%m-%d")

    def is_workday(self, day: date) -> bool:
        key = self._fmt_day(day)
        if key in self._workday_overrides:
            return True
        if key in self._holiday_overrides:
            return False
        if self._calendar is not None:
            return bool(self._calendar.is_workday(day))
        return day.weekday() < 5

    def next_workday_datetime(self, dt: datetime) -> datetime:
        candidate = dt
        time_part = {
            "hour": dt.hour,
            "minute": dt.minute,
            "second": dt.second,
            "microsecond": dt.microsecond,
        }
        while not self.is_workday(candidate.date()):
            candidate = (candidate + timedelta(days=1)).replace(**time_part)
        return candidate
