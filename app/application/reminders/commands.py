from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True, frozen=True)
class CreateReminderCommand:
    text: str
    remind_at: datetime
    timezone: str
    conversation_id: str | None = None
    session_id: str | None = None
    source_channel: str | None = None
    source_user_id: str | None = None
    source_chat_id: str | None = None
    source_thread_id: str | None = None
    dispatch_channel: str = "console"
    dispatch_recipient_id: str = "local-user"
    dispatch_chat_id: str | None = None
    dispatch_thread_id: str | None = None


@dataclass(slots=True, frozen=True)
class HandleReminderReplyCommand:
    reminder_id: str
    reply_text: str


@dataclass(slots=True, frozen=True)
class CancelReminderCommand:
    reminder_id: str


@dataclass(slots=True, frozen=True)
class HandleReminderInboundMessageCommand:
    conversation_id: str | None
    session_id: str | None
    channel: str
    sender_id: str
    message_id: str | None
    root_message_id: str | None
    parent_message_id: str | None
    chat_id: str | None
    thread_id: str | None
    text: str
