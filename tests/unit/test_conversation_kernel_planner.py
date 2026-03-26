from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.complexity import ComplexRequestDetector
from app.application.conversations.kernel.planner import AssistantActionPlanner
from app.application.conversations.kernel.state import (
    AssistantTurnContext,
    CandidateObjectRef,
    LastAssistantAction,
)
from app.application.conversations.kernel.structured_rule_planner import StructuredRulePlanner


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


def _build_disambiguation_context() -> AssistantTurnContext:
    return AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="第二个",
        visible_candidates=[
            CandidateObjectRef(
                object_type="task",
                object_id="t-1",
                title="整理周报",
                score=0.95,
            ),
            CandidateObjectRef(
                object_type="task",
                object_id="t-2",
                title="给客户回电话",
                score=0.9,
            ),
        ],
        dialogue_mode="disambiguation",
        last_assistant_action=LastAssistantAction(
            action_type="complete_task",
            success=True,
            object_type="task",
            summary="请选择要完成的待办。",
        ),
    )


def _build_planner() -> AssistantActionPlanner:
    return AssistantActionPlanner(
        classifier=FailingClassifier(),
        complex_request_detector=ComplexRequestDetector(),
        structured_rule_planner=StructuredRulePlanner(
            now_provider=lambda: datetime(2026, 3, 25, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        ),
        now_provider=lambda: datetime(2026, 3, 25, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )


@pytest.mark.asyncio
async def test_planner_uses_dialogue_state_for_second_candidate() -> None:
    planner = _build_planner()

    plan = await planner.plan(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="第二个",
            raw_payload={"text": "第二个"},
        ),
        turn_context=_build_disambiguation_context(),
    )

    assert plan.action == "complete_task"
    assert plan.object_type == "task"
    assert plan.args["reference_text"] == "第二个"
    assert plan.reasoning == "rules"


@pytest.mark.asyncio
async def test_planner_maps_another_to_second_candidate() -> None:
    planner = _build_planner()

    plan = await planner.plan(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="另一个",
            raw_payload={"text": "另一个"},
        ),
        turn_context=_build_disambiguation_context(),
    )

    assert plan.action == "complete_task"
    assert plan.args["reference_text"] == "第二个"


@pytest.mark.asyncio
async def test_planner_builds_working_set_overview_rule() -> None:
    planner = _build_planner()

    plan = await planner.plan(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="这会话里最近在处理什么",
            raw_payload={"text": "这会话里最近在处理什么"},
        ),
        turn_context=_build_disambiguation_context(),
    )

    assert plan.action == "show_overview"
    assert plan.args["view"] == "working_set"


@pytest.mark.asyncio
async def test_planner_builds_scoped_context_memory_rule() -> None:
    planner = _build_planner()

    plan = await planner.plan(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="把这个背景记到任务里",
            raw_payload={"text": "把这个背景记到任务里"},
        ),
        turn_context=_build_disambiguation_context(),
    )

    assert plan.action == "create_memory"
    assert plan.object_type == "task"
    assert plan.args["memory_type"] == "context"
    assert plan.args["scope_reference_text"] == "这个"


@pytest.mark.asyncio
async def test_planner_builds_natural_reminder_create_rule() -> None:
    planner = _build_planner()

    plan = await planner.plan(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="明天提醒我买药",
            raw_payload={"text": "明天提醒我买药"},
        ),
        turn_context=_build_disambiguation_context(),
    )

    assert plan.action == "create_reminder"
    assert plan.args["text"] == "买药"
    assert plan.args["timezone"] == "Asia/Shanghai"
    assert plan.args["remind_at"] == datetime(2026, 3, 26, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.mark.asyncio
async def test_planner_builds_task_to_reminder_rule() -> None:
    planner = _build_planner()
    turn_context = _build_disambiguation_context()
    turn_context = AssistantTurnContext(
        conversation_id=turn_context.conversation_id,
        session_id=turn_context.session_id,
        latest_user_text="这个待办明早提醒我",
        visible_candidates=[],
        focused_object=None,
        dialogue_mode="normal",
        last_assistant_action=LastAssistantAction(
            action_type="list_tasks",
            success=True,
            object_type="task",
            summary="刚列出待办",
        ),
    )

    plan = await planner.plan(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="这个待办明早提醒我",
            raw_payload={"text": "这个待办明早提醒我"},
        ),
        turn_context=turn_context,
    )

    assert plan.action == "convert_task_to_reminder"
    assert plan.args["timezone"] == "Asia/Shanghai"
    assert plan.args["remind_at"] == datetime(2026, 3, 26, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.mark.asyncio
async def test_planner_builds_reminder_reschedule_rule() -> None:
    planner = _build_planner()
    turn_context = AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="把这个提醒改到后天下午三点",
        dialogue_mode="normal",
        last_assistant_action=LastAssistantAction(
            action_type="list_reminders",
            success=True,
            object_type="reminder",
            summary="刚列出提醒",
        ),
    )

    plan = await planner.plan(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="把这个提醒改到后天下午三点",
            raw_payload={"text": "把这个提醒改到后天下午三点"},
        ),
        turn_context=turn_context,
    )

    assert plan.action == "reschedule_reminder"
    assert plan.args["remind_at"] == datetime(2026, 3, 27, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.mark.asyncio
async def test_planner_builds_reminder_content_update_rule() -> None:
    planner = _build_planner()
    turn_context = AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="把这个提醒改成下班打卡",
        dialogue_mode="normal",
        last_assistant_action=LastAssistantAction(
            action_type="list_reminders",
            success=True,
            object_type="reminder",
            summary="刚列出提醒",
        ),
    )

    plan = await planner.plan(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="把这个提醒改成下班打卡",
            raw_payload={"text": "把这个提醒改成下班打卡"},
        ),
        turn_context=turn_context,
    )

    assert plan.action == "reschedule_reminder"
    assert plan.args["text"] == "下班打卡"
    assert "remind_at" not in plan.args
