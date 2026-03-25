from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.resolver import ReferenceResolver
from app.application.conversations.kernel.state import (
    AssistantTurnContext,
    CandidateObjectRef,
    FocusedObjectRef,
    LastAssistantAction,
)


def _build_turn_context() -> AssistantTurnContext:
    return AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="完成第三个",
        focused_object=FocusedObjectRef(
            object_type="reminder",
            object_id="r-3",
            title="第三个提醒",
        ),
        visible_candidates=[
            CandidateObjectRef(
                object_type="reminder", object_id="r-1", title="第一个提醒", score=0.95
            ),
            CandidateObjectRef(
                object_type="reminder", object_id="r-2", title="第二个提醒", score=0.9
            ),
            CandidateObjectRef(
                object_type="reminder", object_id="r-3", title="第三个提醒", score=0.85
            ),
            CandidateObjectRef(
                object_type="reminder", object_id="r-4", title="第四个提醒", score=0.8
            ),
        ],
        dialogue_mode="disambiguation",
        last_assistant_action=LastAssistantAction(
            action_type="cancel_reminder",
            success=True,
            object_type="reminder",
            object_id="r-3",
            summary="我找到几个可能的对象，你想操作哪一个",
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
                {
                    "object_type": "reminder",
                    "object_id": "r-4",
                    "title": "第四个提醒",
                    "status": "pending",
                },
            ]
        },
    )


def test_完成第三个_命中最近候选列表中的第三项() -> None:
    resolver = ReferenceResolver()
    plan = AssistantActionPlan(
        intent="task_complete",
        action="cancel_reminder",
        object_type="reminder",
        object_id=None,
        args={"reference_text": "第三个"},
        confidence=0.9,
        reasoning="rules",
    )

    resolved = resolver.resolve(plan, turn_context=_build_turn_context())

    assert resolved.status == "ready"
    assert resolved.object_id == "r-3"


def test_取消最后一个提醒_命中列表尾项() -> None:
    resolver = ReferenceResolver()
    plan = AssistantActionPlan(
        intent="reminder_cancel",
        action="cancel_reminder",
        object_type="reminder",
        object_id=None,
        args={"reference_text": "最后一个"},
        confidence=0.9,
        reasoning="rules",
    )

    resolved = resolver.resolve(plan, turn_context=_build_turn_context())

    assert resolved.status == "ready"
    assert resolved.object_id == "r-4"


def test_不是这个_是上一个_回退到聚焦对象的前一项() -> None:
    resolver = ReferenceResolver()
    plan = AssistantActionPlan(
        intent="reminder_cancel",
        action="cancel_reminder",
        object_type="reminder",
        object_id=None,
        args={"reference_text": "上一个"},
        confidence=0.9,
        reasoning="rules",
    )

    resolved = resolver.resolve(plan, turn_context=_build_turn_context())

    assert resolved.status == "ready"
    assert resolved.object_id == "r-2"


def test_没有最近候选列表时_最后一个不回退到_working_set_猜测() -> None:
    resolver = ReferenceResolver()
    turn_context = AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="取消最后一个提醒",
        visible_candidates=[],
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
            ]
        },
    )
    plan = AssistantActionPlan(
        intent="reminder_cancel",
        action="cancel_reminder",
        object_type="reminder",
        object_id=None,
        args={"reference_text": "最后一个"},
        confidence=0.9,
        reasoning="rules",
    )

    resolved = resolver.resolve(plan, turn_context=turn_context)

    assert resolved.status == "unsupported"
