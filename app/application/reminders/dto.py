from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(slots=True, frozen=True)
class ReminderRecurrenceDTO:
    recurrence_type: str
    weekdays: list[str] = field(default_factory=list)
    hour: int = 9
    minute: int = 0


@dataclass(slots=True, frozen=True)
class ReminderDTO:
    reminder_id: str
    text: str
    remind_at: datetime
    timezone: str
    status: str
    recurrence: ReminderRecurrenceDTO | None = None
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
class ReminderBulkCancelSummaryDTO:
    total_canceled: int
    one_off_canceled: int
    recurring_canceled: int
    canceled_items: list[ReminderDTO] = field(default_factory=list)


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
    response_text: str | None = None
    decision: Literal["completed", "needs_confirmation", "pass_to_kernel"] = "pass_to_kernel"
    match_source: str | None = None
