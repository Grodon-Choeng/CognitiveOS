import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.executor import AssistantExecutor
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.renderer import AssistantResponseRenderer
from app.application.conversations.kernel.resolver import ReferenceResolver
from app.application.conversations.kernel.results import (
    AssistantConfirmationResult,
    AssistantDisambiguationResult,
)
from app.application.conversations.kernel.state import (
    AssistantTurnContext,
    CandidateObjectRef,
    FocusedObjectRef,
)


class DummyTaskService:
    async def create_task(self, command):  # noqa: ANN001
        raise AssertionError

    async def get_task(self, task_id):  # noqa: ANN001
        raise AssertionError

    async def complete_task(self, command):  # noqa: ANN001
        raise AssertionError

    async def cancel_task(self, command):  # noqa: ANN001
        raise AssertionError

    async def complete_latest_task(self, *, conversation_id: str, session_id: str):  # noqa: ARG002
        raise AssertionError

    async def cancel_latest_task(self, *, conversation_id: str, session_id: str):  # noqa: ARG002
        raise AssertionError

    async def complete_matching_task(
        self, *, conversation_id: str, session_id: str, title_hint: str
    ):  # noqa: ARG002
        raise AssertionError

    async def cancel_matching_task(self, *, conversation_id: str, session_id: str, title_hint: str):  # noqa: ARG002
        raise AssertionError

    async def attach_reminder(self, *, task_id: str, reminder_id: str):  # noqa: ARG002
        raise AssertionError

    async def list_tasks(self, query):  # noqa: ANN001
        raise AssertionError


class DummyReminderService:
    async def create_reminder(self, command):  # noqa: ANN001
        raise AssertionError

    async def get_reminder(self, reminder_id):  # noqa: ANN001
        raise AssertionError

    async def cancel_reminder(self, command):  # noqa: ANN001
        raise AssertionError

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

    async def archive_latest_memory(self, *, conversation_id: str, session_id: str):  # noqa: ARG002
        raise AssertionError

    async def archive_matching_memory(
        self, *, conversation_id: str, session_id: str, content_hint: str
    ):  # noqa: ARG002
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


def _build_executor() -> AssistantExecutor:
    return AssistantExecutor(
        task_service=DummyTaskService(),
        reminder_service=DummyReminderService(),
        memory_service=DummyMemoryService(),
        overview_service=DummyOverviewService(),
        resolver=ReferenceResolver(),
    )


def _render_result(
    result: AssistantConfirmationResult | AssistantDisambiguationResult,
    *,
    turn_context: AssistantTurnContext,
) -> str:
    return AssistantResponseRenderer().render(result, turn_context=turn_context)


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


def _build_turn_context() -> AssistantTurnContext:
    return AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="取消刚才那个",
        focused_object=FocusedObjectRef(
            object_type="reminder",
            object_id="r-1",
            title="买药提醒",
        ),
        visible_candidates=[
            CandidateObjectRef(
                object_type="reminder", object_id="r-1", title="买药提醒", score=0.95
            ),
            CandidateObjectRef(
                object_type="reminder", object_id="r-2", title="买咖啡提醒", score=0.9
            ),
        ],
    )


@pytest.mark.asyncio
async def test_我找到几个可能的对象_你想操作哪一个() -> None:
    executor = _build_executor()
    turn_context = _build_turn_context()
    result = await executor.execute(
        AssistantActionPlan(
            intent="reminder_cancel",
            action="cancel_reminder",
            object_type="reminder",
            object_id=None,
            args={"reference_text": "买"},
            confidence=0.9,
            reasoning="rules",
        ),
        command=_build_command("取消刚才那个"),
        turn_context=turn_context,
    )

    assert isinstance(result, AssistantDisambiguationResult)
    assert result.prompt == "我找到几个可能的对象，你想操作哪一个？"
    response_text = _render_result(result, turn_context=turn_context)
    assert "1. 买药提醒" in response_text
    assert "2. 买咖啡提醒" in response_text


@pytest.mark.asyncio
async def test_我理解成你要操作这条记录_先帮你确认一下() -> None:
    executor = _build_executor()
    turn_context = _build_turn_context()
    result = await executor.execute(
        AssistantActionPlan(
            intent="reminder_cancel",
            action="cancel_reminder",
            object_type="reminder",
            object_id=None,
            args={"reference_text": "刚才那个"},
            confidence=0.7,
            reasoning="rules",
        ),
        command=_build_command("取消刚才那个"),
        turn_context=turn_context,
    )

    assert isinstance(result, AssistantConfirmationResult)
    assert result.prompt == "我理解成你要操作这条记录，先帮你确认一下。"
    response_text = _render_result(result, turn_context=turn_context)
    assert "买药提醒" in response_text
    assert "回复“是的”" in response_text


@pytest.mark.asyncio
async def test_当对象不唯一时_进入_needs_disambiguation() -> None:
    executor = _build_executor()
    turn_context = _build_turn_context()

    result = await executor.execute(
        AssistantActionPlan(
            intent="reminder_cancel",
            action="cancel_reminder",
            object_type="reminder",
            object_id=None,
            args={"reference_text": "买"},
            confidence=0.95,
            reasoning="rules",
        ),
        command=_build_command("取消买那个"),
        turn_context=turn_context,
    )

    assert isinstance(result, AssistantDisambiguationResult)
    assert len(result.candidates) == 2


@pytest.mark.asyncio
async def test_当置信不足但可猜时_进入_needs_confirmation() -> None:
    executor = _build_executor()
    turn_context = _build_turn_context()

    result = await executor.execute(
        AssistantActionPlan(
            intent="reminder_cancel",
            action="cancel_reminder",
            object_type="reminder",
            object_id=None,
            args={"reference_text": "刚才那个"},
            confidence=0.7,
            reasoning="rules",
        ),
        command=_build_command("取消刚才那个"),
        turn_context=turn_context,
    )

    assert isinstance(result, AssistantConfirmationResult)
    assert result.preview_text == "买药提醒"


@pytest.mark.asyncio
async def test_取消这个_低置信时进入_confirmation_而不是直接取消() -> None:
    executor = _build_executor()
    turn_context = _build_turn_context()

    result = await executor.execute(
        AssistantActionPlan(
            intent="reminder_cancel",
            action="cancel_reminder",
            object_type="reminder",
            object_id=None,
            args={"reference_text": "这个"},
            confidence=0.7,
            reasoning="rules",
        ),
        command=_build_command("取消这个"),
        turn_context=turn_context,
    )

    assert isinstance(result, AssistantConfirmationResult)
    assert result.preview_text == "买药提醒"
    response_text = _render_result(result, turn_context=turn_context)
    assert "买药提醒" in response_text
    assert "回复“是的”" in response_text
