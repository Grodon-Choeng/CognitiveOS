from typing import Protocol

from app.domain.reminders.entities import Reminder
from app.domain.reminders.value_objects import ReminderId


class ReminderRepository(Protocol):
    async def add(self, reminder: Reminder) -> None: ...

    async def get(self, reminder_id: ReminderId) -> Reminder | None: ...

    async def list(
        self,
        *,
        conversation_id: str | None = None,
        session_id: str | None = None,
        status: str | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> list[Reminder]: ...

    async def get_by_dispatch_message_id(self, dispatch_message_id: str) -> Reminder | None: ...

    async def get_latest_pending_by_conversation(
        self,
        conversation_id: str,
    ) -> Reminder | None: ...

    async def get_latest_pending_by_dispatch_chat(
        self,
        channel: str,
        recipient_id: str,
        chat_id: str,
        thread_id: str | None = None,
    ) -> Reminder | None: ...

    async def get_latest_pending_by_dispatch(
        self,
        channel: str,
        recipient_id: str,
    ) -> Reminder | None: ...

    async def update(self, reminder: Reminder) -> None: ...
