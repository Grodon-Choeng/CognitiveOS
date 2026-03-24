from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.resolver import ReferenceResolver
from app.application.conversations.kernel.state import (
    AssistantTurnContext,
    CandidateObjectRef,
    FocusedObjectRef,
)


def _build_turn_context() -> AssistantTurnContext:
    return AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text="完成第二个",
        focused_object=FocusedObjectRef(
            object_type="reminder",
            object_id="r-1",
            title="买药",
        ),
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
        metadata={
            "pending_tasks": [
                {
                    "object_type": "task",
                    "object_id": "t-1",
                    "title": "整理周报",
                    "status": "pending",
                },
                {
                    "object_type": "task",
                    "object_id": "t-2",
                    "title": "给客户回电话",
                    "status": "pending",
                },
            ],
            "pending_reminders": [
                {
                    "object_type": "reminder",
                    "object_id": "r-1",
                    "title": "买药",
                    "status": "pending",
                },
                {
                    "object_type": "reminder",
                    "object_id": "r-2",
                    "title": "买水果",
                    "status": "pending",
                },
            ],
        },
    )


def test_reference_resolver_uses_focused_object_for_pronoun() -> None:
    resolver = ReferenceResolver()
    plan = AssistantActionPlan(
        intent="reminder_cancel",
        action="cancel_reminder",
        object_type="reminder",
        object_id=None,
        args={"reference_text": "刚才那个"},
        confidence=0.9,
        reasoning="rules",
    )

    resolved = resolver.resolve(plan, turn_context=_build_turn_context())

    assert resolved.status == "ready"
    assert resolved.object_id == "r-1"


def test_reference_resolver_supports_second_visible_candidate() -> None:
    resolver = ReferenceResolver()
    plan = AssistantActionPlan(
        intent="task_complete",
        action="complete_task",
        object_type="task",
        object_id=None,
        args={"reference_text": "第二个"},
        confidence=0.9,
        reasoning="rules",
    )

    resolved = resolver.resolve(plan, turn_context=_build_turn_context())

    assert resolved.status == "ready"
    assert resolved.object_id == "t-2"


def test_reference_resolver_supports_keyword_hint() -> None:
    resolver = ReferenceResolver()
    plan = AssistantActionPlan(
        intent="reminder_cancel",
        action="cancel_reminder",
        object_type="reminder",
        object_id=None,
        args={"reference_text": "买药那个提醒"},
        confidence=0.9,
        reasoning="rules",
    )

    resolved = resolver.resolve(plan, turn_context=_build_turn_context())

    assert resolved.status == "ready"
    assert resolved.object_id == "r-1"


def test_reference_resolver_returns_disambiguation_for_multiple_matches() -> None:
    resolver = ReferenceResolver()
    plan = AssistantActionPlan(
        intent="reminder_cancel",
        action="cancel_reminder",
        object_type="reminder",
        object_id=None,
        args={"reference_text": "买"},
        confidence=0.9,
        reasoning="rules",
    )

    resolved = resolver.resolve(plan, turn_context=_build_turn_context())

    assert resolved.status == "needs_disambiguation"
    assert [candidate.object_id for candidate in resolved.candidates] == ["r-1", "r-2"]
