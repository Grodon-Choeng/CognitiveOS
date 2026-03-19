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
