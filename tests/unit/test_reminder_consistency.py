from datetime import UTC, datetime

import pytest

from app.application.reminders.commands import CancelAllRemindersCommand, CreateReminderCommand
from app.application.reminders.queries import ListRemindersQuery
from app.application.reminders.service import ReminderApplicationService
from app.domain.reminders.entities import Reminder, ReminderStatus
from app.domain.reminders.value_objects import ReminderId, ReminderRecurrence, ReminderSchedule
from tests.unit.test_reminder_service import (
    FakeConversationContextResolver,
    FakeReminderRepository,
    FakeReminderWorkflowGateway,
    create_fake_unit_of_work_factory,
)


def _build_service() -> tuple[
    ReminderApplicationService,
    FakeReminderRepository,
    FakeReminderWorkflowGateway,
]:
    repository = FakeReminderRepository()
    workflow_gateway = FakeReminderWorkflowGateway()
    service = ReminderApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        workflow_gateway=workflow_gateway,
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    return service, repository, workflow_gateway


def _build_legacy_malformed_reminder(
    *,
    conversation_id: str,
    session_id: str,
) -> Reminder:
    return Reminder(
        reminder_id=ReminderId.new(),
        text=(
            "上班打卡，晚上9点05提醒我下班打卡，然后本周六需要加班，"
            "也得提醒我打卡，其他非工作日需要提醒打卡的我会另行通知"
        ),
        schedule=ReminderSchedule(
            remind_at=datetime(2026, 3, 27, 9, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
        ),
        status=ReminderStatus.PENDING,
        workflow_id="reminder:legacy-invalid",
        conversation_id=conversation_id,
        session_id=session_id,
    )


@pytest.mark.asyncio
async def test_cancel_all_reminders_removes_everything_visible_in_active_reminder_list() -> None:
    service, repository, workflow_gateway = _build_service()
    one_off = await service.create_reminder(
        CreateReminderCommand(
            text="明早买药",
            remind_at=datetime(2026, 3, 27, 1, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )
    recurring = await service.create_reminder(
        CreateReminderCommand(
            text="工作日上班打卡",
            remind_at=datetime(2026, 3, 27, 1, 55, tzinfo=UTC),
            timezone="Asia/Shanghai",
            recurrence=ReminderRecurrence(
                recurrence_type="weekly_by_weekdays",
                weekdays=("mon", "tue", "wed", "thu", "fri"),
                hour=9,
                minute=55,
            ),
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )
    malformed = _build_legacy_malformed_reminder(
        conversation_id="conversation-1",
        session_id="session-1",
    )
    repository.items[str(malformed.reminder_id.value)] = malformed

    visible_before = await service.list_active_reminders(
        ListRemindersQuery(
            conversation_id="conversation-1",
            session_id="session-1",
            limit=10,
        )
    )

    assert [item.reminder_id for item in visible_before.items] == [
        recurring.reminder_id,
        one_off.reminder_id,
    ]

    canceled = await service.cancel_all_reminders(
        CancelAllRemindersCommand(
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )

    visible_after = await service.list_active_reminders(
        ListRemindersQuery(
            conversation_id="conversation-1",
            session_id="session-1",
            limit=10,
        )
    )

    assert canceled.total_canceled == 2
    assert canceled.one_off_canceled == 1
    assert canceled.recurring_canceled == 1
    assert visible_after.items == []
    assert repository.items[one_off.reminder_id].status == ReminderStatus.CANCELED
    assert repository.items[recurring.reminder_id].status == ReminderStatus.CANCELED
    assert repository.items[str(malformed.reminder_id.value)].status == ReminderStatus.PENDING
    assert workflow_gateway.canceled_workflows == [
        recurring.workflow_id or "",
        one_off.workflow_id or "",
    ]


@pytest.mark.asyncio
async def test_list_active_reminders_filters_malformed_legacy_reminder() -> None:
    service, repository, _ = _build_service()
    clean = await service.create_reminder(
        CreateReminderCommand(
            text="晚上复盘",
            remind_at=datetime(2026, 3, 27, 12, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )
    malformed = _build_legacy_malformed_reminder(
        conversation_id="conversation-1",
        session_id="session-1",
    )
    repository.items[str(malformed.reminder_id.value)] = malformed

    visible = await service.list_active_reminders(
        ListRemindersQuery(
            conversation_id="conversation-1",
            session_id="session-1",
            limit=10,
        )
    )

    assert [item.reminder_id for item in visible.items] == [clean.reminder_id]
    assert all("另行通知" not in item.text for item in visible.items)


@pytest.mark.asyncio
async def test_cancel_all_reminders_cancels_recurring_definition_and_relist_hides_it() -> None:
    service, repository, workflow_gateway = _build_service()
    recurring = await service.create_reminder(
        CreateReminderCommand(
            text="工作日晨会提醒",
            remind_at=datetime(2026, 3, 27, 1, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            recurrence=ReminderRecurrence(
                recurrence_type="weekly_by_weekdays",
                weekdays=("mon", "tue", "wed", "thu", "fri"),
                hour=9,
                minute=0,
            ),
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )

    visible_before = await service.list_active_reminders(
        ListRemindersQuery(conversation_id="conversation-1", session_id="session-1")
    )
    canceled = await service.cancel_all_reminders(
        CancelAllRemindersCommand(conversation_id="conversation-1", session_id="session-1")
    )
    visible_after = await service.list_active_reminders(
        ListRemindersQuery(conversation_id="conversation-1", session_id="session-1")
    )

    assert [item.reminder_id for item in visible_before.items] == [recurring.reminder_id]
    assert canceled.recurring_canceled == 1
    assert visible_after.items == []
    assert repository.items[recurring.reminder_id].status == ReminderStatus.CANCELED
    assert workflow_gateway.canceled_workflows == [recurring.workflow_id or ""]


@pytest.mark.asyncio
async def test_constraint_memory_objects_do_not_pollute_active_reminder_list() -> None:
    service, repository, _ = _build_service()
    recurring = await service.create_reminder(
        CreateReminderCommand(
            text="工作日上午上班打卡",
            remind_at=datetime(2026, 3, 27, 1, 55, tzinfo=UTC),
            timezone="Asia/Shanghai",
            recurrence=ReminderRecurrence(
                recurrence_type="weekly_by_weekdays",
                weekdays=("mon", "tue", "wed", "thu", "fri"),
                hour=9,
                minute=55,
            ),
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )
    one_off = await service.create_reminder(
        CreateReminderCommand(
            text="本周六加班打卡",
            remind_at=datetime(2026, 3, 28, 1, 55, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )
    constraint_like_reminder_id = ReminderId.new()
    repository.items[str(constraint_like_reminder_id.value)] = Reminder(
        reminder_id=constraint_like_reminder_id,
        text="其他非工作日需要提醒打卡的我会另行通知",
        schedule=ReminderSchedule(
            remind_at=datetime(2026, 3, 29, 1, 55, tzinfo=UTC),
            timezone="Asia/Shanghai",
        ),
        status=ReminderStatus.PENDING,
        workflow_id="reminder:constraint-like",
        conversation_id="conversation-1",
        session_id="session-1",
    )

    visible = await service.list_active_reminders(
        ListRemindersQuery(conversation_id="conversation-1", session_id="session-1", limit=10)
    )

    assert [item.reminder_id for item in visible.items] == [
        one_off.reminder_id,
        recurring.reminder_id,
    ]
    assert [item.text for item in visible.items] == ["本周六加班打卡", "工作日上午上班打卡"]
    assert all("另行通知" not in item.text for item in visible.items)
