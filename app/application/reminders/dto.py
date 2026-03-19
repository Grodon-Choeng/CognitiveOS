from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class ReminderDTO:
    reminder_id: str
    text: str
    remind_at: datetime
    timezone: str
    status: str
    workflow_id: str | None = None


@dataclass(slots=True, frozen=True)
class ReminderReplyDTO:
    reminder_id: str
    reply_text: str
    accepted: bool
    status: str
