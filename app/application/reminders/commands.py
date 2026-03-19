from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class CreateReminderCommand:
    text: str
    remind_at: datetime
    timezone: str
    dispatch_channel: str = "console"
    dispatch_recipient_id: str = "local-user"


@dataclass(slots=True, frozen=True)
class HandleReminderReplyCommand:
    reminder_id: str
    reply_text: str
