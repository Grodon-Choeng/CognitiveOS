from dataclasses import dataclass
from enum import StrEnum

from app.domain.reminders.value_objects import ReminderId, ReminderSchedule


class ReminderStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELED = "canceled"


@dataclass(slots=True)
class Reminder:
    reminder_id: ReminderId
    text: str
    schedule: ReminderSchedule
    status: ReminderStatus = ReminderStatus.PENDING
    workflow_id: str | None = None
    last_user_reply: str | None = None
