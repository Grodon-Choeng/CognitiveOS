from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType

import pytest

from app.application.reminders.commands import CreateReminderCommand, HandleReminderReplyCommand
from app.application.reminders.errors import ReminderNotFoundError
from app.application.reminders.ports import (
    ReminderDispatchTarget,
    ReminderUnitOfWork,
    ReminderWorkflowGateway,
)
from app.application.reminders.service import ReminderApplicationService
from app.domain.reminders.entities import Reminder
from app.domain.reminders.repository import ReminderRepository
from app.domain.reminders.value_objects import ReminderId


class FakeReminderRepository(ReminderRepository):
    def __init__(self) -> None:
        self.items: dict[str, Reminder] = {}

    async def add(self, reminder: Reminder) -> None:
        self.items[str(reminder.reminder_id.value)] = reminder

    async def get(self, reminder_id: ReminderId) -> Reminder | None:
        return self.items.get(str(reminder_id.value))

    async def update(self, reminder: Reminder) -> None:
        self.items[str(reminder.reminder_id.value)] = reminder


class FakeReminderUnitOfWork(ReminderUnitOfWork):
    def __init__(self, repository: FakeReminderRepository) -> None:
        self.reminders: ReminderRepository = repository
        self.commit_count = 0

    async def __aenter__(self) -> "FakeReminderUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc, tb)

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        return None


@dataclass
class StartedWorkflow:
    reminder_id: str
    dispatch_target: ReminderDispatchTarget


class FakeReminderWorkflowGateway(ReminderWorkflowGateway):
    def __init__(self) -> None:
        self.started: list[StartedWorkflow] = []
        self.recorded_replies: list[tuple[str, str]] = []

    async def start_reminder(
        self,
        reminder: Reminder,
        dispatch_target: ReminderDispatchTarget,
    ) -> str:
        reminder_id = str(reminder.reminder_id.value)
        self.started.append(
            StartedWorkflow(
                reminder_id=reminder_id,
                dispatch_target=dispatch_target,
            )
        )
        return f"reminder:{reminder_id}"

    async def record_user_reply(self, workflow_id: str, reply_text: str) -> None:
        self.recorded_replies.append((workflow_id, reply_text))


@pytest.mark.asyncio
async def test_create_reminder_persists_and_starts_workflow() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=lambda: FakeReminderUnitOfWork(repository),
        workflow_gateway=workflow_gateway,
    )

    result = await service.create_reminder(
        CreateReminderCommand(
            text="明天上午九点提醒我打卡",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            dispatch_channel="console",
            dispatch_recipient_id="user-1",
        )
    )

    saved = repository.items[result.reminder_id]
    assert result.workflow_id == f"reminder:{result.reminder_id}"
    assert saved.workflow_id == result.workflow_id
    assert workflow_gateway.started[0].dispatch_target.channel == "console"
    assert workflow_gateway.started[0].dispatch_target.recipient_id == "user-1"


@pytest.mark.asyncio
async def test_handle_reply_updates_reminder_and_signals_workflow() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=lambda: FakeReminderUnitOfWork(repository),
        workflow_gateway=workflow_gateway,
    )

    created = await service.create_reminder(
        CreateReminderCommand(
            text="提醒我提交日报",
            remind_at=datetime(2026, 3, 20, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
        )
    )

    reply_result = await service.handle_reply(
        HandleReminderReplyCommand(
            reminder_id=created.reminder_id,
            reply_text="我已经提交了",
        )
    )

    saved = repository.items[created.reminder_id]
    assert reply_result.accepted is True
    assert reply_result.status == "completed"
    assert saved.last_user_reply == "我已经提交了"
    assert saved.status.value == "completed"
    assert workflow_gateway.recorded_replies == [(created.workflow_id or "", "我已经提交了")]


@pytest.mark.asyncio
async def test_handle_reply_raises_when_reminder_not_found() -> None:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=lambda: FakeReminderUnitOfWork(repository),
        workflow_gateway=workflow_gateway,
    )

    with pytest.raises(ReminderNotFoundError):
        await service.handle_reply(
            HandleReminderReplyCommand(
                reminder_id="00000000-0000-0000-0000-000000000001",
                reply_text="收到",
            )
        )
