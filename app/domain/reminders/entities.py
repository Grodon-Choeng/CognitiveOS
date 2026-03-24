from dataclasses import dataclass
from enum import StrEnum

from app.domain.reminders.value_objects import ReminderId, ReminderSchedule


class ReminderStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"


@dataclass(slots=True)
class Reminder:
    reminder_id: ReminderId
    text: str
    schedule: ReminderSchedule
    status: ReminderStatus = ReminderStatus.PENDING
    workflow_id: str | None = None
    conversation_id: str | None = None
    session_id: str | None = None
    dispatch_channel: str | None = None
    dispatch_recipient_id: str | None = None
    dispatch_chat_id: str | None = None
    dispatch_thread_id: str | None = None
    dispatch_message_id: str | None = None
    last_user_reply: str | None = None
    linked_task_id: str | None = None
    failure_stage: str | None = None
    failure_reason_code: str | None = None
    retryable: bool = True
