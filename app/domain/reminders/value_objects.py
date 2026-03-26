from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

_VALID_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_WEEKDAY_INDEX = {day: index for index, day in enumerate(_VALID_WEEKDAYS)}


@dataclass(slots=True, frozen=True)
class ReminderRecurrence:
    recurrence_type: str
    weekdays: tuple[str, ...] = field(default_factory=tuple)
    hour: int = 9
    minute: int = 0

    def __post_init__(self) -> None:
        if self.recurrence_type != "weekly_by_weekdays":
            raise ValueError(f"不支持的 reminder recurrence 类型：{self.recurrence_type}")
        if not self.weekdays:
            raise ValueError("循环提醒至少需要一个 weekday。")
        if any(day not in _WEEKDAY_INDEX for day in self.weekdays):
            raise ValueError("循环提醒包含不支持的 weekday。")
        if not 0 <= self.hour <= 23:
            raise ValueError("循环提醒 hour 必须在 0-23 之间。")
        if not 0 <= self.minute <= 59:
            raise ValueError("循环提醒 minute 必须在 0-59 之间。")

    def to_payload(self) -> dict[str, object]:
        return {
            "recurrence_type": self.recurrence_type,
            "weekdays": list(self.weekdays),
            "hour": self.hour,
            "minute": self.minute,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> "ReminderRecurrence":
        raw_weekdays = payload.get("weekdays")
        weekdays = (
            tuple(item for item in raw_weekdays if isinstance(item, str))
            if isinstance(raw_weekdays, list)
            else tuple()
        )
        hour = payload.get("hour")
        minute = payload.get("minute")
        return cls(
            recurrence_type=str(payload["recurrence_type"]),
            weekdays=weekdays,
            hour=int(hour) if isinstance(hour, int) else 9,
            minute=int(minute) if isinstance(minute, int) else 0,
        )


@dataclass(slots=True, frozen=True)
class ReminderId:
    value: UUID

    @classmethod
    def new(cls) -> "ReminderId":
        return cls(value=uuid4())

    @classmethod
    def from_string(cls, value: str) -> "ReminderId":
        return cls(value=UUID(value))


@dataclass(slots=True, frozen=True)
class ReminderSchedule:
    remind_at: datetime
    timezone: str
    recurrence: ReminderRecurrence | None = None

    def __post_init__(self) -> None:
        if self.remind_at.tzinfo is None or self.remind_at.utcoffset() is None:
            raise ValueError("提醒时间必须包含明确的时区信息。")
        if not self.timezone.strip():
            raise ValueError("提醒时区不能为空。")

    @property
    def is_recurring(self) -> bool:
        return self.recurrence is not None


def next_remind_at_for_recurrence(
    recurrence: ReminderRecurrence,
    *,
    timezone: str,
    after: datetime,
) -> datetime:
    if after.tzinfo is None or after.utcoffset() is None:
        raise ValueError("计算循环提醒时间时 after 必须带时区。")
    zone = ZoneInfo(timezone)
    local_after = after.astimezone(zone)
    allowed_weekdays = {_WEEKDAY_INDEX[day] for day in recurrence.weekdays}
    for day_offset in range(8):
        candidate_date = local_after.date() + timedelta(days=day_offset)
        if candidate_date.weekday() not in allowed_weekdays:
            continue
        candidate = datetime(
            candidate_date.year,
            candidate_date.month,
            candidate_date.day,
            recurrence.hour,
            recurrence.minute,
            tzinfo=zone,
        )
        if candidate > local_after:
            return candidate
    raise ValueError("无法计算下一个循环提醒时间。")
