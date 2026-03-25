from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.planner import AssistantActionPlanner
from app.application.conversations.kernel.state import (
    AssistantTurnContext,
    CandidateObjectRef,
    LastAssistantAction,
)


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
