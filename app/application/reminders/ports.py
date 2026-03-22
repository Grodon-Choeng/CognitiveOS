from collections.abc import Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol, Self

from app.domain.reminders.entities import Reminder
from app.domain.reminders.repository import ReminderRepository


@dataclass(slots=True, frozen=True)
class ReminderDispatchTarget:
    channel: str = "console"
    recipient_id: str = "local-user"


class ReminderUnitOfWork(Protocol):
    reminders: ReminderRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


ReminderUnitOfWorkFactory = Callable[[], ReminderUnitOfWork]


class ReminderWorkflowGateway(Protocol):
    async def start_reminder(
        self,
        reminder: Reminder,
        dispatch_target: ReminderDispatchTarget,
    ) -> str: ...

    async def record_user_reply(self, workflow_id: str, reply_text: str) -> None: ...

    async def cancel_reminder(self, workflow_id: str) -> None: ...
