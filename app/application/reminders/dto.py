from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class ReminderDTO:
    reminder_id: str
    text: str
    remind_at: datetime
    timezone: str
    status: str
    linked_task_id: str | None = None
    failure_stage: str | None = None
    failure_reason_code: str | None = None
    retryable: bool = True
    conversation_id: str | None = None
    session_id: str | None = None
    workflow_id: str | None = None


@dataclass(slots=True, frozen=True)
class ReminderListDTO:
    items: list[ReminderDTO]


@dataclass(slots=True, frozen=True)
class ReminderReplyDTO:
    reminder_id: str
    reply_text: str
    accepted: bool
    status: str


@dataclass(slots=True, frozen=True)
class ReminderInboundMessageResult:
    handled: bool
    reminder_id: str | None = None
    reason: str | None = None
