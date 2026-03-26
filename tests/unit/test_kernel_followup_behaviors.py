from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.executor import AssistantExecutor
from app.application.conversations.kernel.planner import AssistantActionPlanner
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.renderer import AssistantResponseRenderer
from app.application.conversations.kernel.resolver import ReferenceResolver
from app.application.conversations.kernel.state import (
    AssistantTurnContext,
    CandidateObjectRef,
    FocusedObjectRef,
    LastAssistantAction,
)
from app.application.memory.dto import MemoryDTO
from app.application.reminders.dto import ReminderDTO
from app.application.tasks.dto import TaskDTO


class FailingClassifier:
    async def classify(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
        context_text: str | None = None,
        prefer_rules: bool = False,
    ) -> object:
        _ = (command, conversation_id, session_id, context_text, prefer_rules)
        raise AssertionError("本测试不应走到 classifier")


def _build_planner() -> AssistantActionPlanner:
    return AssistantActionPlanner(
        classifier=FailingClassifier(),
        now_provider=lambda: datetime(2026, 3, 25, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )


def _build_context() -> AssistantTurnContext:
    return AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="不是这个，是另一个",
        visible_candidates=[
            CandidateObjectRef(object_type="task", object_id="t-1", title="第一个任务", score=0.95),
            CandidateObjectRef(object_type="task", object_id="t-2", title="第二个任务", score=0.9),
            CandidateObjectRef(object_type="task", object_id="t-3", title="第三个任务", score=0.85),
        ],
        dialogue_mode="disambiguation",
        last_assistant_action=LastAssistantAction(
            action_type="complete_task",
            success=True,
            object_type="task",
            summary="我找到几个可能的对象，你想操作哪一个",
        ),
    )


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


class RecordingTaskService:
    def __init__(self) -> None:
        self.completed_task_ids: list[str] = []
        self.titles_by_id: dict[str, str] = {}

    async def create_task(self, command):  # noqa: ANN001
        raise AssertionError

    async def get_task(self, task_id: str) -> TaskDTO:
        return TaskDTO(
            task_id=task_id,
            title=self.titles_by_id.get(task_id, f"任务 {task_id}"),
            created_at=datetime(2026, 3, 25, 9, 0, tzinfo=ZoneInfo("UTC")),
            status="pending",
        )

    async def complete_task(self, command) -> TaskDTO:  # noqa: ANN001
        self.completed_task_ids.append(command.task_id)
        return TaskDTO(
            task_id=command.task_id,
            title=self.titles_by_id.get(command.task_id, f"任务 {command.task_id}"),
            created_at=datetime(2026, 3, 25, 9, 0, tzinfo=ZoneInfo("UTC")),
            status="completed",
        )

    async def cancel_task(self, command):  # noqa: ANN001
        raise AssertionError

    async def attach_reminder(self, *, task_id: str, reminder_id: str):  # noqa: ARG002
        raise AssertionError

    async def list_tasks(self, query):  # noqa: ANN001
        raise AssertionError


class RecordingReminderService:
    def __init__(self) -> None:
        self.created_reminder_payloads: list[tuple[str, datetime, str]] = []
        self.canceled_reminder_ids: list[str] = []
        self.rescheduled_reminder_ids: list[str] = []
        self.last_reschedule_when: datetime | None = None
        self.titles_by_id: dict[str, str] = {}

    async def create_reminder(self, command) -> ReminderDTO:  # noqa: ANN001
        self.created_reminder_payloads.append((command.text, command.remind_at, command.timezone))
        return ReminderDTO(
            reminder_id="r-created",
            text=command.text,
            remind_at=command.remind_at,
            timezone=command.timezone,
            status="pending",
        )

    async def get_reminder(self, reminder_id: str) -> ReminderDTO:
        return ReminderDTO(
            reminder_id=reminder_id,
            text=self.titles_by_id.get(reminder_id, f"提醒 {reminder_id}"),
            remind_at=datetime(2026, 3, 26, 6, 0, tzinfo=ZoneInfo("UTC")),
            timezone="Asia/Shanghai",
            status="pending",
        )

    async def cancel_reminder(self, command) -> ReminderDTO:  # noqa: ANN001
        self.canceled_reminder_ids.append(command.reminder_id)
        return ReminderDTO(
            reminder_id=command.reminder_id,
            text=self.titles_by_id.get(command.reminder_id, f"提醒 {command.reminder_id}"),
            remind_at=datetime(2026, 3, 26, 6, 0, tzinfo=ZoneInfo("UTC")),
            timezone="Asia/Shanghai",
            status="canceled",
        )

    async def link_task(self, *, reminder_id: str, task_id: str):  # noqa: ARG002
        raise AssertionError

    async def retry_failed_reminder(self, command):  # noqa: ANN001
        raise AssertionError

    async def reschedule_reminder(self, command) -> ReminderDTO:  # noqa: ANN001
        self.rescheduled_reminder_ids.append(command.reminder_id)
        self.last_reschedule_when = command.remind_at
        return ReminderDTO(
            reminder_id=command.reminder_id,
            text=self.titles_by_id.get(command.reminder_id, f"提醒 {command.reminder_id}"),
            remind_at=command.remind_at,
            timezone=command.timezone,
            status="pending",
        )

    async def list_reminders(self, query):  # noqa: ANN001
        raise AssertionError


class RecordingMemoryService:
    def __init__(self) -> None:
        self.created_memory_payloads: list[tuple[str, str | None]] = []

    async def create_memory(self, command) -> MemoryDTO:  # noqa: ANN001
        self.created_memory_payloads.append((command.content, command.memory_type))
        return MemoryDTO(
            memory_id="m-created",
            content=command.content,
            created_at=datetime(2026, 3, 25, 9, 0, tzinfo=ZoneInfo("UTC")),
            status="active",
            memory_type=command.memory_type or "note",
            scope_object_type=command.scope_object_type,
            scope_object_id=command.scope_object_id,
        )

    async def archive_memory(self, command):  # noqa: ANN001
        raise AssertionError

    async def list_memories(self, query):  # noqa: ANN001
        raise AssertionError


class DummyOverviewService:
    async def get_overview(self, query):  # noqa: ANN001
        raise AssertionError

    async def get_today_view(self, query):  # noqa: ANN001
        raise AssertionError

    async def get_working_set_view(self, query):  # noqa: ANN001
        raise AssertionError


def _build_executor(
    *,
    task_service: RecordingTaskService | None = None,
    reminder_service: RecordingReminderService | None = None,
    memory_service: RecordingMemoryService | None = None,
) -> AssistantExecutor:
    return AssistantExecutor(
        task_service=task_service or RecordingTaskService(),
        reminder_service=reminder_service or RecordingReminderService(),
        memory_service=memory_service or RecordingMemoryService(),
        overview_service=DummyOverviewService(),
        resolver=ReferenceResolver(),
    )


async def _run_kernel_turn(
    *,
    text: str,
    turn_context: AssistantTurnContext,
    task_service: RecordingTaskService | None = None,
    reminder_service: RecordingReminderService | None = None,
    memory_service: RecordingMemoryService | None = None,
) -> tuple[AssistantActionPlan, object, str | None]:
    planner = _build_planner()
    executor = _build_executor(
        task_service=task_service,
        reminder_service=reminder_service,
        memory_service=memory_service,
    )
    renderer = AssistantResponseRenderer()
    command = _build_command(text)
    plan = await planner.plan(command, turn_context=turn_context)
    result = await executor.execute(
        plan=plan,
        command=command,
        turn_context=turn_context,
    )
    response_text = None if result is None else renderer.render(result, turn_context=turn_context)
    return plan, result, response_text


@pytest.mark.asyncio
async def test_不是这个_是另一个_仍然走_followup_规则() -> None:
    task_service = RecordingTaskService()
    task_service.titles_by_id = {
        "t-1": "第一个任务",
        "t-2": "第二个任务",
        "t-3": "第三个任务",
    }

    plan, result, response_text = await _run_kernel_turn(
        text="不是这个，是另一个",
        turn_context=_build_context(),
        task_service=task_service,
    )

    assert plan.action == "complete_task"
    assert plan.args["reference_text"] == "第二个"
    assert task_service.completed_task_ids == ["t-2"]
    assert getattr(result, "object_id", None) == "t-2"
    assert response_text is not None
    assert "第二个任务" in response_text


@pytest.mark.asyncio
async def test_明天提醒我买药_创建提醒并返回自然确认() -> None:
    reminder_service = RecordingReminderService()
    turn_context = AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="明天提醒我买药",
    )

    plan, result, response_text = await _run_kernel_turn(
        text="明天提醒我买药",
        turn_context=turn_context,
        reminder_service=reminder_service,
    )

    assert plan.action == "create_reminder"
    assert plan.status == "ready"
    assert reminder_service.created_reminder_payloads == [
        ("买药", datetime(2026, 3, 26, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")), "Asia/Shanghai")
    ]
    assert result is not None
    assert getattr(result, "object_id", None) == "r-created"
    assert response_text is not None
    assert "已经记成提醒了" in response_text
    assert "买药" in response_text
    assert "2026-03-26 09:00" in response_text


@pytest.mark.asyncio
async def test_记一下我不想早上八点前被提醒_写入记忆并自然回复() -> None:
    memory_service = RecordingMemoryService()
    turn_context = AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="记一下我不想早上八点前被提醒",
    )

    plan, result, response_text = await _run_kernel_turn(
        text="记一下我不想早上八点前被提醒",
        turn_context=turn_context,
        memory_service=memory_service,
    )

    assert plan.action == "create_memory"
    assert plan.args["memory_type"] == "note"
    assert memory_service.created_memory_payloads == [("我不想早上八点前被提醒", "note")]
    assert result is not None
    assert getattr(result, "object_id", None) == "m-created"
    assert response_text is not None
    assert "记下了" in response_text
    assert "我不想早上八点前被提醒" in response_text


@pytest.mark.asyncio
async def test_改成明天下午_生成_reminder_改期计划() -> None:
    reminder_service = RecordingReminderService()
    reminder_service.titles_by_id = {
        "r-1": "第一个提醒",
        "r-2": "第二个提醒",
        "r-3": "第三个提醒",
    }
    turn_context = AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="把倒数第二个改成明天下午",
        visible_candidates=[
            CandidateObjectRef(
                object_type="reminder",
                object_id="r-1",
                title="第一个提醒",
                score=0.95,
            ),
            CandidateObjectRef(
                object_type="reminder",
                object_id="r-2",
                title="第二个提醒",
                score=0.9,
            ),
            CandidateObjectRef(
                object_type="reminder",
                object_id="r-3",
                title="第三个提醒",
                score=0.85,
            ),
        ],
        last_assistant_action=LastAssistantAction(
            action_type="list_reminders",
            success=True,
            object_type="reminder",
            summary="刚列出提醒列表",
        ),
        metadata={
            "pending_reminders": [
                {
                    "object_type": "reminder",
                    "object_id": "r-1",
                    "title": "第一个提醒",
                    "status": "pending",
                },
                {
                    "object_type": "reminder",
                    "object_id": "r-2",
                    "title": "第二个提醒",
                    "status": "pending",
                },
                {
                    "object_type": "reminder",
                    "object_id": "r-3",
                    "title": "第三个提醒",
                    "status": "pending",
                },
            ]
        },
    )

    plan, result, response_text = await _run_kernel_turn(
        text="把倒数第二个改成明天下午",
        turn_context=turn_context,
        reminder_service=reminder_service,
    )

    assert plan.action == "reschedule_reminder"
    assert plan.args["reference_text"] == "倒数第二个"
    assert plan.args["timezone"] == "Asia/Shanghai"
    assert reminder_service.rescheduled_reminder_ids == ["r-2"]
    assert result is not None
    assert getattr(result, "object_id", None) == "r-2"
    assert response_text is not None
    assert "已经帮你改时间了" in response_text


@pytest.mark.asyncio
async def test_完成第二个_会完成第二条待办() -> None:
    task_service = RecordingTaskService()
    task_service.titles_by_id = {
        "t-1": "第一个任务",
        "t-2": "第二个任务",
    }
    turn_context = AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="完成第二个",
        visible_candidates=[
            CandidateObjectRef(object_type="task", object_id="t-1", title="第一个任务", score=0.95),
            CandidateObjectRef(object_type="task", object_id="t-2", title="第二个任务", score=0.9),
        ],
        metadata={
            "pending_tasks": [
                {
                    "object_type": "task",
                    "object_id": "t-1",
                    "title": "第一个任务",
                    "status": "pending",
                },
                {
                    "object_type": "task",
                    "object_id": "t-2",
                    "title": "第二个任务",
                    "status": "pending",
                },
            ]
        },
    )

    plan, result, response_text = await _run_kernel_turn(
        text="完成第二个",
        turn_context=turn_context,
        task_service=task_service,
    )

    assert plan.status == "ready"
    assert task_service.completed_task_ids == ["t-2"]
    assert result is not None
    assert result.object_id == "t-2"
    assert response_text is not None
    assert "已经帮你完成这个待办了" in response_text


@pytest.mark.asyncio
async def test_取消刚才那个_会取消聚焦提醒() -> None:
    reminder_service = RecordingReminderService()
    reminder_service.titles_by_id = {
        "r-1": "取快递提醒",
        "r-2": "买药提醒",
    }
    turn_context = AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="取消刚才那个",
        focused_object=FocusedObjectRef(
            object_type="reminder",
            object_id="r-2",
            title="买药提醒",
        ),
        visible_candidates=[
            CandidateObjectRef(
                object_type="reminder",
                object_id="r-1",
                title="取快递提醒",
                score=0.95,
            ),
            CandidateObjectRef(
                object_type="reminder",
                object_id="r-2",
                title="买药提醒",
                score=0.9,
            ),
        ],
        metadata={
            "pending_reminders": [
                {
                    "object_type": "reminder",
                    "object_id": "r-1",
                    "title": "取快递提醒",
                    "status": "pending",
                },
                {
                    "object_type": "reminder",
                    "object_id": "r-2",
                    "title": "买药提醒",
                    "status": "pending",
                },
            ]
        },
    )

    plan, result, response_text = await _run_kernel_turn(
        text="取消刚才那个",
        turn_context=turn_context,
        reminder_service=reminder_service,
    )

    assert plan.status == "ready"
    assert reminder_service.canceled_reminder_ids == ["r-2"]
    assert result is not None
    assert result.object_id == "r-2"
    assert response_text is not None
    assert "这条提醒我已经取消了" in response_text


@pytest.mark.asyncio
async def test_列表展示后的_取消第二个_优先命中_visible_candidates() -> None:
    reminder_service = RecordingReminderService()
    reminder_service.titles_by_id = {
        "r-1": "买药提醒",
        "r-2": "交房租提醒",
    }
    turn_context = AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="取消第二个",
        visible_candidates=[
            CandidateObjectRef(
                object_type="reminder",
                object_id="r-1",
                title="买药提醒",
                score=0.95,
            ),
            CandidateObjectRef(
                object_type="reminder",
                object_id="r-2",
                title="交房租提醒",
                score=0.9,
            ),
        ],
        last_assistant_action=LastAssistantAction(
            action_type="list_reminders",
            success=True,
            object_type="reminder",
            summary="刚列出提醒列表",
        ),
        metadata={
            "pending_reminders": [
                {
                    "object_type": "reminder",
                    "object_id": "r-9",
                    "title": "旧的最近提醒",
                    "status": "pending",
                },
                {
                    "object_type": "reminder",
                    "object_id": "r-8",
                    "title": "更旧的提醒",
                    "status": "pending",
                },
            ]
        },
    )

    plan, result, response_text = await _run_kernel_turn(
        text="取消第二个",
        turn_context=turn_context,
        reminder_service=reminder_service,
    )

    assert plan.action == "cancel_reminder"
    assert reminder_service.canceled_reminder_ids == ["r-2"]
    assert result is not None
    assert getattr(result, "object_id", None) == "r-2"
    assert response_text is not None
    assert "交房租提醒" in response_text
