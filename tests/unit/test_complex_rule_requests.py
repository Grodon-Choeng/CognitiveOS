from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.complexity import ComplexRequestDetector
from app.application.conversations.kernel.executor import AssistantExecutor
from app.application.conversations.kernel.planner import AssistantActionPlanner
from app.application.conversations.kernel.renderer import AssistantResponseRenderer
from app.application.conversations.kernel.resolver import ReferenceResolver
from app.application.conversations.kernel.rule_executor import RuleExecutor
from app.application.conversations.kernel.state import AssistantTurnContext, LastAssistantAction
from app.application.conversations.kernel.structured_rule_planner import StructuredRulePlanner
from app.application.memory.dto import MemoryDTO
from app.application.reminders.dto import ReminderDTO


class FailingClassifier:
    async def classify(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("复杂规则测试不应退回 classifier。")


class RecordingReminderService:
    def __init__(self) -> None:
        self.created_commands: list[tuple[str, datetime, str]] = []

    async def create_reminder(self, command) -> ReminderDTO:  # noqa: ANN001
        self.created_commands.append((command.text, command.remind_at, command.timezone))
        return ReminderDTO(
            reminder_id=f"r-{len(self.created_commands)}",
            text=command.text,
            remind_at=command.remind_at,
            timezone=command.timezone,
            status="pending",
        )

    async def get_reminder(self, reminder_id: str) -> ReminderDTO:  # pragma: no cover
        raise AssertionError(reminder_id)

    async def cancel_reminder(self, command):  # noqa: ANN001, pragma: no cover
        raise AssertionError(command)

    async def link_task(self, *, reminder_id: str, task_id: str):  # noqa: ARG002, pragma: no cover
        raise AssertionError

    async def retry_failed_reminder(self, command):  # noqa: ANN001, pragma: no cover
        raise AssertionError(command)

    async def reschedule_reminder(self, command):  # noqa: ANN001, pragma: no cover
        raise AssertionError(command)

    async def list_reminders(self, query):  # noqa: ANN001, pragma: no cover
        raise AssertionError(query)


class RecordingMemoryService:
    def __init__(self) -> None:
        self.created_commands: list[tuple[str, str | None]] = []

    async def create_memory(self, command) -> MemoryDTO:  # noqa: ANN001
        self.created_commands.append((command.content, command.memory_type))
        return MemoryDTO(
            memory_id="m-1",
            content=command.content,
            created_at=datetime(2026, 3, 25, 9, 0, tzinfo=ZoneInfo("UTC")),
            status="active",
            memory_type=command.memory_type or "note",
            scope_object_type=command.scope_object_type,
            scope_object_id=command.scope_object_id,
        )

    async def archive_memory(self, command):  # noqa: ANN001, pragma: no cover
        raise AssertionError(command)

    async def list_memories(self, query):  # noqa: ANN001, pragma: no cover
        raise AssertionError(query)


class DummyTaskService:
    async def create_task(self, command):  # noqa: ANN001, pragma: no cover
        raise AssertionError(command)

    async def get_task(self, task_id: str):  # pragma: no cover
        raise AssertionError(task_id)

    async def complete_task(self, command):  # noqa: ANN001, pragma: no cover
        raise AssertionError(command)

    async def cancel_task(self, command):  # noqa: ANN001, pragma: no cover
        raise AssertionError(command)

    async def attach_reminder(self, *, task_id: str, reminder_id: str):  # noqa: ARG002, pragma: no cover
        raise AssertionError

    async def list_tasks(self, query):  # noqa: ANN001, pragma: no cover
        raise AssertionError(query)


class DummyOverviewService:
    async def get_overview(self, query):  # noqa: ANN001, pragma: no cover
        raise AssertionError(query)

    async def get_today_view(self, query):  # noqa: ANN001, pragma: no cover
        raise AssertionError(query)

    async def get_working_set_view(self, query):  # noqa: ANN001, pragma: no cover
        raise AssertionError(query)


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


def _build_turn_context(**overrides: object) -> AssistantTurnContext:
    return AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text=None,
        **overrides,
    )


def _build_planner() -> AssistantActionPlanner:
    def now_provider() -> datetime:
        return datetime(2026, 3, 25, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    return AssistantActionPlanner(
        classifier=FailingClassifier(),
        complex_request_detector=ComplexRequestDetector(),
        structured_rule_planner=StructuredRulePlanner(now_provider=now_provider),
        now_provider=now_provider,
    )


def _build_executor(
    *,
    reminder_service: RecordingReminderService,
    memory_service: RecordingMemoryService,
) -> AssistantExecutor:
    return AssistantExecutor(
        task_service=DummyTaskService(),
        reminder_service=reminder_service,
        memory_service=memory_service,
        overview_service=DummyOverviewService(),
        resolver=ReferenceResolver(),
        rule_executor=RuleExecutor(
            reminder_service=reminder_service,
            memory_service=memory_service,
        ),
    )


COMPLEX_TEXT = (
    "以后工作日的早上9点55提醒我上班打卡，晚上9点05提醒我下班打卡，"
    "然后本周六需要加班，也得提醒我打卡，其他非工作日需要提醒打卡的我会另行通知"
)


@pytest.mark.asyncio
async def test_复杂规则请求不会被压成一条_reminder() -> None:
    planner = _build_planner()
    reminder_service = RecordingReminderService()
    memory_service = RecordingMemoryService()
    executor = _build_executor(
        reminder_service=reminder_service,
        memory_service=memory_service,
    )

    plan = await planner.plan(_build_command(COMPLEX_TEXT), turn_context=_build_turn_context())
    result = await executor.execute(
        plan=plan,
        command=_build_command(COMPLEX_TEXT),
        turn_context=_build_turn_context(),
    )
    response_text = AssistantResponseRenderer().render(result, turn_context=_build_turn_context())

    assert plan.action == "preview_structured_rule_plan"
    assert reminder_service.created_commands == []
    assert "工作日 09:55" in response_text
    assert "本周六" in response_text
    assert "已经记成提醒了" not in response_text


@pytest.mark.asyncio
async def test_复杂规则请求默认进入_confirmation_preview() -> None:
    planner = _build_planner()

    plan = await planner.plan(_build_command(COMPLEX_TEXT), turn_context=_build_turn_context())

    assert plan.action == "preview_structured_rule_plan"
    assert plan.args["request_kind"] == "rule_with_overrides"
    structured_plan = plan.args["structured_plan"]
    assert len(structured_plan["rule_items"]) == 2
    assert len(structured_plan["overrides"]) == 1
    assert len(structured_plan["constraints"]) == 1


@pytest.mark.asyncio
async def test_确认后会拆成多个动作执行() -> None:
    planner = _build_planner()
    reminder_service = RecordingReminderService()
    memory_service = RecordingMemoryService()
    executor = _build_executor(
        reminder_service=reminder_service,
        memory_service=memory_service,
    )

    preview_plan = await planner.plan(
        _build_command(COMPLEX_TEXT),
        turn_context=_build_turn_context(),
    )
    confirmation_context = _build_turn_context(
        dialogue_mode="confirmation",
        metadata={"pending_complex_plan": preview_plan.args["structured_plan"]},
        last_assistant_action=LastAssistantAction(
            action_type="execute_structured_rule_plan",
            success=True,
            summary="复杂规则等待确认。",
        ),
    )

    execute_plan = await planner.plan(_build_command("按这个来"), turn_context=confirmation_context)
    result = await executor.execute(
        plan=execute_plan,
        command=_build_command("按这个来"),
        turn_context=confirmation_context,
    )
    response_text = AssistantResponseRenderer().render(result, turn_context=confirmation_context)

    assert execute_plan.action == "execute_structured_rule_plan"
    assert len(reminder_service.created_commands) == 2
    assert len(memory_service.created_commands) == 1
    assert "已创建 2 条单次提醒" in response_text


@pytest.mark.asyncio
async def test_其他非工作日我另行通知_不会被误建成_reminder_文本() -> None:
    planner = _build_planner()
    reminder_service = RecordingReminderService()
    memory_service = RecordingMemoryService()
    executor = _build_executor(
        reminder_service=reminder_service,
        memory_service=memory_service,
    )

    preview_plan = await planner.plan(
        _build_command(COMPLEX_TEXT),
        turn_context=_build_turn_context(),
    )
    confirmation_context = _build_turn_context(
        dialogue_mode="confirmation",
        metadata={"pending_complex_plan": preview_plan.args["structured_plan"]},
        last_assistant_action=LastAssistantAction(
            action_type="execute_structured_rule_plan",
            success=True,
            summary="复杂规则等待确认。",
        ),
    )

    execute_plan = await planner.plan(_build_command("确认"), turn_context=confirmation_context)
    await executor.execute(
        plan=execute_plan,
        command=_build_command("确认"),
        turn_context=confirmation_context,
    )

    assert all("另行通知" not in text for text, _, _ in reminder_service.created_commands)
    assert "另行通知" in memory_service.created_commands[0][0]


@pytest.mark.asyncio
async def test_普通简单_reminder_请求不受影响() -> None:
    planner = _build_planner()
    reminder_service = RecordingReminderService()
    memory_service = RecordingMemoryService()
    executor = _build_executor(
        reminder_service=reminder_service,
        memory_service=memory_service,
    )
    command = _build_command("明天提醒我买药")

    plan = await planner.plan(command, turn_context=_build_turn_context())
    result = await executor.execute(
        plan=plan,
        command=command,
        turn_context=_build_turn_context(),
    )
    response_text = AssistantResponseRenderer().render(result, turn_context=_build_turn_context())

    assert plan.action == "create_reminder"
    assert len(reminder_service.created_commands) == 1
    assert memory_service.created_commands == []
    assert "已经记成提醒了" in response_text
