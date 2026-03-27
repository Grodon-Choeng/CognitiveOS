from datetime import UTC, datetime

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.complexity import ComplexRequestDetector
from app.application.conversations.kernel.executor import AssistantExecutor
from app.application.conversations.kernel.planner import AssistantActionPlanner
from app.application.conversations.kernel.renderer import AssistantResponseRenderer
from app.application.conversations.kernel.resolver import ReferenceResolver
from app.application.conversations.kernel.rule_executor import RuleExecutor
from app.application.conversations.kernel.state import (
    AssistantTurnContext,
    CandidateObjectRef,
    LastAssistantAction,
)
from app.application.conversations.kernel.structured_rule_planner import StructuredRulePlanner
from app.application.memory.dto import MemoryListDTO
from app.application.overview.dto import OverviewDTO
from app.application.reminders.commands import AcknowledgeReminderCommand, CreateReminderCommand
from app.application.reminders.queries import ListRemindersQuery
from app.application.reminders.service import ReminderApplicationService
from app.application.tasks.dto import TaskListDTO
from app.domain.reminders.value_objects import ReminderRecurrence
from tests.unit.test_reminder_service import (
    FakeConversationContextResolver,
    FakeReminderRepository,
    FakeReminderWorkflowGateway,
    create_fake_unit_of_work_factory,
)


class FailingClassifier:
    async def classify(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("本组 reminder lifecycle 测试不应退回 classifier。")


class DummyTaskService:
    async def list_tasks(self, query) -> TaskListDTO:  # noqa: ANN001
        _ = query
        return TaskListDTO(items=[])


class DummyMemoryService:
    async def list_memories(self, query) -> MemoryListDTO:  # noqa: ANN001
        _ = query
        return MemoryListDTO(items=[])


class DummyOverviewService:
    async def get_overview(self, query) -> OverviewDTO:  # noqa: ANN001
        _ = query
        return OverviewDTO(
            conversation_id="conversation-1",
            session_id="session-1",
            pending_reminders=[],
            pending_tasks=[],
            active_memories=[],
            recent_activity=[],
        )

    async def get_today_view(self, query):  # noqa: ANN001, ANN201
        raise AssertionError(query)

    async def get_working_set_view(self, query):  # noqa: ANN001, ANN201
        raise AssertionError(query)


def _fixed_now() -> datetime:
    return datetime(2026, 3, 27, 10, 0, tzinfo=UTC)


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
        now_provider=_fixed_now,
    )
    return service, repository, workflow_gateway


def _build_command(text: str) -> HandleInboundConversationMessageCommand:
    return HandleInboundConversationMessageCommand(
        channel="web",
        message_type="text",
        user_identity="user-1",
        external_message_id=None,
        root_message_id=None,
        parent_message_id=None,
        chat_id=None,
        thread_id=None,
        text=text,
        raw_payload={"text": text},
    )


def _build_planner() -> AssistantActionPlanner:
    return AssistantActionPlanner(
        classifier=FailingClassifier(),
        complex_request_detector=ComplexRequestDetector(),
        structured_rule_planner=StructuredRulePlanner(now_provider=_fixed_now),
        now_provider=_fixed_now,
    )


def _build_executor(reminder_service: ReminderApplicationService) -> AssistantExecutor:
    return AssistantExecutor(
        task_service=DummyTaskService(),  # type: ignore[arg-type]
        reminder_service=reminder_service,
        memory_service=DummyMemoryService(),  # type: ignore[arg-type]
        overview_service=DummyOverviewService(),  # type: ignore[arg-type]
        resolver=ReferenceResolver(),
        rule_executor=RuleExecutor(
            reminder_service=reminder_service,
            memory_service=DummyMemoryService(),  # type: ignore[arg-type]
            now_provider=_fixed_now,
        ),
    )


@pytest.mark.asyncio
async def test_past_one_off_reminder_is_not_returned_in_active_reminder_list() -> None:
    service, _, _ = _build_service()
    past_one_off = await service.create_reminder(
        CreateReminderCommand(
            text="打卡",
            remind_at=datetime(2026, 3, 25, 5, 5, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )
    future_one_off = await service.create_reminder(
        CreateReminderCommand(
            text="明天买药",
            remind_at=datetime(2026, 3, 28, 1, 0, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )

    visible = await service.list_active_reminders(
        ListRemindersQuery(conversation_id="conversation-1", session_id="session-1", limit=10)
    )

    assert [item.reminder_id for item in visible.items] == [future_one_off.reminder_id]
    assert all(item.reminder_id != past_one_off.reminder_id for item in visible.items)


@pytest.mark.asyncio
async def test_user_acknowledges_past_one_off_reminder_and_it_disappears_from_active_list() -> None:
    service, repository, workflow_gateway = _build_service()
    created = await service.create_reminder(
        CreateReminderCommand(
            text="打卡",
            remind_at=datetime(2026, 3, 25, 5, 5, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )

    acknowledged = await service.acknowledge_reminder(
        AcknowledgeReminderCommand(
            reminder_id=created.reminder_id,
            reply_text="这个提醒已经提醒过了呀",
        )
    )
    visible_after = await service.list_active_reminders(
        ListRemindersQuery(conversation_id="conversation-1", session_id="session-1", limit=10)
    )

    assert acknowledged.status == "completed"
    assert repository.items[created.reminder_id].status.value == "completed"
    assert workflow_gateway.recorded_replies == [
        (created.workflow_id or "", "这个提醒已经提醒过了呀")
    ]
    assert visible_after.items == []


@pytest.mark.asyncio
async def test_acknowledging_fired_reminder_updates_state_and_relist_is_consistent() -> None:
    service, repository, _ = _build_service()
    planner = _build_planner()
    executor = _build_executor(service)
    renderer = AssistantResponseRenderer()
    created = await service.create_reminder(
        CreateReminderCommand(
            text="打卡",
            remind_at=datetime(2026, 3, 25, 5, 5, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )

    turn_context = AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="这个提醒已经提醒过了呀",
        visible_candidates=[
            CandidateObjectRef(
                object_type="reminder",
                object_id=created.reminder_id,
                title=created.text,
                score=0.9,
            )
        ],
        last_assistant_action=LastAssistantAction(
            action_type="list_reminders",
            success=True,
            object_type="reminder",
            object_id=None,
            summary="你现在有 1 个提醒。",
        ),
        metadata={
            "pending_reminders": [
                {
                    "object_type": "reminder",
                    "object_id": created.reminder_id,
                    "title": created.text,
                    "status": "pending",
                    "when": created.remind_at.isoformat(),
                }
            ],
            "pending_tasks": [],
            "active_memories": [],
        },
    )

    plan = await planner.plan(_build_command("这个提醒已经提醒过了呀"), turn_context=turn_context)
    result = await executor.execute(
        plan,
        command=_build_command("这个提醒已经提醒过了呀"),
        turn_context=turn_context,
    )
    visible_after = await service.list_active_reminders(
        ListRemindersQuery(conversation_id="conversation-1", session_id="session-1", limit=10)
    )

    assert plan.action == "acknowledge_reminder"
    assert result is not None
    assert getattr(result, "action", None) == "acknowledge_reminder"
    assert repository.items[created.reminder_id].status.value == "completed"
    assert visible_after.items == []
    assert "不会继续出现" in renderer.render(result, turn_context=turn_context)


@pytest.mark.asyncio
async def test_recurring_reminder_remains_visible_in_active_list_after_one_off_acknowledgement(
) -> None:
    service, _, _ = _build_service()
    one_off = await service.create_reminder(
        CreateReminderCommand(
            text="一次性打卡",
            remind_at=datetime(2026, 3, 25, 5, 5, tzinfo=UTC),
            timezone="Asia/Shanghai",
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )
    recurring = await service.create_reminder(
        CreateReminderCommand(
            text="工作日打卡",
            remind_at=datetime(2026, 3, 28, 1, 0, tzinfo=UTC),
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

    await service.acknowledge_reminder(
        AcknowledgeReminderCommand(
            reminder_id=one_off.reminder_id,
            reply_text="这个提醒已经提醒过了呀",
        )
    )
    visible = await service.list_active_reminders(
        ListRemindersQuery(conversation_id="conversation-1", session_id="session-1", limit=10)
    )

    assert [item.reminder_id for item in visible.items] == [recurring.reminder_id]
