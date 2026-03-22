from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4


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

    def __post_init__(self) -> None:
        if self.remind_at.tzinfo is None or self.remind_at.utcoffset() is None:
            raise ValueError("提醒时间必须包含明确的时区信息。")
        if not self.timezone.strip():
            raise ValueError("提醒时区不能为空。")
