from typing import Protocol

from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.referential_rules import infer_memory_type
from app.application.conversations.kernel.state import AssistantTurnContext


class PlannerDecision(Protocol):
    intent: str
    content: str | None
    status: str | None
    remind_at: object | None
    timezone: str | None
    source: str


def build_context_text(turn_context: AssistantTurnContext) -> str | None:
    lines: list[str] = []
    if turn_context.metadata.get("pending_reminders"):
        lines.append("pending_reminders:")
        for reminder in turn_context.metadata["pending_reminders"]:
            if isinstance(reminder, dict) and isinstance(reminder.get("title"), str):
                lines.append(f"- {reminder['title']}")
    if turn_context.metadata.get("pending_tasks"):
        lines.append("pending_tasks:")
        for task in turn_context.metadata["pending_tasks"]:
            if isinstance(task, dict) and isinstance(task.get("title"), str):
                lines.append(f"- {task['title']}")
    if turn_context.metadata.get("active_memories"):
        lines.append("active_memories:")
        for memory in turn_context.metadata["active_memories"]:
            if isinstance(memory, dict) and isinstance(memory.get("title"), str):
                lines.append(f"- {memory['title']}")
    return "\n".join(lines) if lines else None


def normalize_decision_to_plan(decision: PlannerDecision) -> AssistantActionPlan:
    source_confidence = 0.91 if decision.source == "rules" else 0.84

    if decision.intent == "greeting":
        return AssistantActionPlan(
            intent=decision.intent,
            action="reply_greeting",
            object_type=None,
            object_id=None,
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "help_show":
        return AssistantActionPlan(
            intent=decision.intent,
            action="show_help",
            object_type=None,
            object_id=None,
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "overview_show":
        return AssistantActionPlan(
            intent=decision.intent,
            action="show_overview",
            object_type=None,
            object_id=None,
            args={"view": "default"},
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "activity_show":
        return AssistantActionPlan(
            intent=decision.intent,
            action="show_activity",
            object_type=None,
            object_id=None,
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "task_create" and decision.content is not None:
        return AssistantActionPlan(
            intent=decision.intent,
            action="create_task",
            object_type="task",
            object_id=None,
            args={"title": decision.content},
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "task_list":
        return AssistantActionPlan(
            intent=decision.intent,
            action="list_tasks",
            object_type="task",
            object_id=None,
            args={"status": decision.status, "query": decision.content},
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "task_complete":
        return AssistantActionPlan(
            intent=decision.intent,
            action="complete_task",
            object_type="task",
            object_id=None,
            args={"reference_text": decision.content},
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "task_cancel":
        return AssistantActionPlan(
            intent=decision.intent,
            action="cancel_task",
            object_type="task",
            object_id=None,
            args={"reference_text": decision.content},
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if (
        decision.intent == "reminder_create"
        and decision.content is not None
        and decision.remind_at is not None
        and decision.timezone is not None
    ):
        return AssistantActionPlan(
            intent=decision.intent,
            action="create_reminder",
            object_type="reminder",
            object_id=None,
            args={
                "text": decision.content,
                "remind_at": decision.remind_at,
                "timezone": decision.timezone,
            },
            confidence=max(source_confidence, 0.88),
            reasoning=decision.source,
        )
    if decision.intent == "reminder_cancel":
        return AssistantActionPlan(
            intent=decision.intent,
            action="cancel_reminder",
            object_type="reminder",
            object_id=None,
            args={"reference_text": decision.content},
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if (
        decision.intent == "reminder_reschedule"
        and decision.remind_at is not None
        and decision.timezone is not None
    ):
        return AssistantActionPlan(
            intent=decision.intent,
            action="reschedule_reminder",
            object_type="reminder",
            object_id=None,
            args={
                "reference_text": decision.content,
                "remind_at": decision.remind_at,
                "timezone": decision.timezone,
            },
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "reminder_retry_failed":
        return AssistantActionPlan(
            intent=decision.intent,
            action="retry_failed_reminder",
            object_type="reminder",
            object_id=None,
            args={"reference_text": decision.content, "status": "failed"},
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "reminder_list":
        return AssistantActionPlan(
            intent=decision.intent,
            action="list_reminders",
            object_type="reminder",
            object_id=None,
            args={"status": decision.status, "query": decision.content},
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if (
        decision.intent == "task_to_reminder"
        and decision.remind_at is not None
        and decision.timezone is not None
    ):
        return AssistantActionPlan(
            intent=decision.intent,
            action="convert_task_to_reminder",
            object_type="task",
            object_id=None,
            args={
                "reference_text": decision.content,
                "remind_at": decision.remind_at,
                "timezone": decision.timezone,
            },
            confidence=max(source_confidence, 0.88),
            reasoning=decision.source,
        )
    if decision.intent == "reminder_to_task":
        return AssistantActionPlan(
            intent=decision.intent,
            action="convert_reminder_to_task",
            object_type="reminder",
            object_id=None,
            args={"reference_text": decision.content},
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "memory_write" and decision.content is not None:
        return AssistantActionPlan(
            intent=decision.intent,
            action="create_memory",
            object_type="memory",
            object_id=None,
            args={
                "content": decision.content,
                "memory_type": infer_memory_type(decision.content),
            },
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "memory_archive":
        return AssistantActionPlan(
            intent=decision.intent,
            action="archive_memory",
            object_type="memory",
            object_id=None,
            args={"reference_text": decision.content},
            confidence=source_confidence,
            reasoning=decision.source,
        )
    if decision.intent == "memory_list":
        return AssistantActionPlan(
            intent=decision.intent,
            action="list_memories",
            object_type="memory",
            object_id=None,
            args={"status": decision.status, "query": decision.content},
            confidence=source_confidence,
            reasoning=decision.source,
        )
    return AssistantActionPlan(
        intent=decision.intent,
        action=None,
        object_type=None,
        object_id=None,
        status="unsupported",
        confidence=0.0,
        reasoning=decision.source,
    )
