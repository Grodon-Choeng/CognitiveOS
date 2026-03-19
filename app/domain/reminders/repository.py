from typing import Protocol

from app.domain.reminders.entities import Reminder
from app.domain.reminders.value_objects import ReminderId


class ReminderRepository(Protocol):
    async def add(self, reminder: Reminder) -> None: ...

    async def get(self, reminder_id: ReminderId) -> Reminder | None: ...

    async def update(self, reminder: Reminder) -> None: ...
