from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.executor import AssistantExecutor
from app.application.conversations.kernel.planner import AssistantActionPlanner
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.resolver import ReferenceResolver
from app.application.conversations.kernel.state import (
    AssistantTurnContext,
    CandidateObjectRef,
    FocusedObjectRef,
    LastAssistantAction,
)
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

    async def create_task(self, command):  # noqa: ANN001
        raise AssertionError

    async def get_task(self, task_id: str) -> TaskDTO:
        return TaskDTO(
            task_id=task_id,
            title=f"任务 {task_id}",
            created_at=datetime(2026, 3, 25, 9, 0, tzinfo=ZoneInfo("UTC")),
            status="pending",
        )

    async def complete_task(self, command) -> TaskDTO:  # noqa: ANN001
        self.completed_task_ids.append(command.task_id)
        return TaskDTO(
            task_id=command.task_id,
            title=f"任务 {command.task_id}",
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
        self.canceled_reminder_ids: list[str] = []

    async def create_reminder(self, command):  # noqa: ANN001
        raise AssertionError

    async def get_reminder(self, reminder_id: str) -> ReminderDTO:
        return ReminderDTO(
            reminder_id=reminder_id,
            text=f"提醒 {reminder_id}",
            remind_at=datetime(2026, 3, 26, 6, 0, tzinfo=ZoneInfo("UTC")),
            timezone="Asia/Shanghai",
            status="pending",
        )

    async def cancel_reminder(self, command) -> ReminderDTO:  # noqa: ANN001
        self.canceled_reminder_ids.append(command.reminder_id)
        return ReminderDTO(
            reminder_id=command.reminder_id,
            text=f"提醒 {command.reminder_id}",
            remind_at=datetime(2026, 3, 26, 6, 0, tzinfo=ZoneInfo("UTC")),
            timezone="Asia/Shanghai",
            status="canceled",
        )

    async def link_task(self, *, reminder_id: str, task_id: str):  # noqa: ARG002
        raise AssertionError

    async def retry_failed_reminder(self, command):  # noqa: ANN001
        raise AssertionError

    async def reschedule_reminder(self, command):  # noqa: ANN001
        raise AssertionError

    async def list_reminders(self, query):  # noqa: ANN001
        raise AssertionError


class DummyMemoryService:
    async def create_memory(self, command):  # noqa: ANN001
        raise AssertionError

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
) -> AssistantExecutor:
    return AssistantExecutor(
        task_service=task_service or RecordingTaskService(),
        reminder_service=reminder_service or RecordingReminderService(),
        memory_service=DummyMemoryService(),
        overview_service=DummyOverviewService(),
        resolver=ReferenceResolver(),
    )


@pytest.mark.asyncio
async def test_不是这个_是另一个_仍然走_followup_规则() -> None:
    planner = _build_planner()

    plan = await planner.plan(_build_command("不是这个，是另一个"), turn_context=_build_context())

    assert plan.action == "complete_task"
    assert plan.args["reference_text"] == "第二个"


@pytest.mark.asyncio
async def test_改成明天下午_生成_reminder_改期计划() -> None:
    planner = _build_planner()
    turn_context = AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="把倒数第二个改成明天下午",
        last_assistant_action=LastAssistantAction(
            action_type="list_reminders",
            success=True,
            object_type="reminder",
            summary="刚列出提醒列表",
        ),
    )

    plan = await planner.plan(_build_command("把倒数第二个改成明天下午"), turn_context=turn_context)

    assert plan.action == "reschedule_reminder"
    assert plan.args["reference_text"] == "倒数第二个"
    assert plan.args["timezone"] == "Asia/Shanghai"


@pytest.mark.asyncio
async def test_完成第二个_会完成第二条待办() -> None:
    task_service = RecordingTaskService()
    executor = _build_executor(task_service=task_service)
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

    result = await executor.execute(
        plan=AssistantActionPlan(
            intent="task_complete",
            action="complete_task",
            object_type="task",
            object_id=None,
            args={"reference_text": "第二个"},
            confidence=0.95,
            reasoning="rules",
        ),
        command=_build_command("完成第二个"),
        turn_context=turn_context,
    )

    assert task_service.completed_task_ids == ["t-2"]
    assert result is not None
    assert result.object_id == "t-2"


@pytest.mark.asyncio
async def test_取消刚才那个_会取消聚焦提醒() -> None:
    reminder_service = RecordingReminderService()
    executor = _build_executor(reminder_service=reminder_service)
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

    result = await executor.execute(
        plan=AssistantActionPlan(
            intent="reminder_cancel",
            action="cancel_reminder",
            object_type="reminder",
            object_id=None,
            args={"reference_text": "刚才那个"},
            confidence=0.95,
            reasoning="rules",
        ),
        command=_build_command("取消刚才那个"),
        turn_context=turn_context,
    )

    assert reminder_service.canceled_reminder_ids == ["r-2"]
    assert result is not None
    assert result.object_id == "r-2"
