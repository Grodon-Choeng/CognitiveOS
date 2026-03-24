from datetime import datetime
from typing import Any, Protocol, cast

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.state import AssistantTurnContext

_REFERENCE_FOLLOWUPS = {
    "这个",
    "那个",
    "刚才那个",
    "就刚才那个",
    "第一个",
    "第二个",
    "最后一个",
    "另一个",
    "不是这个，是另一个",
}
_CONFIRM_YES = {"是", "是的", "对", "对的", "好的", "好"}
_MEMORY_PREFIXES = ("记住", "记一下", "记下", "memo")
_WORKING_SET_REQUESTS = {
    "这会话里最近在处理什么",
    "最近在处理什么",
    "当前工作集",
    "working set",
}


class PlannerDecision(Protocol):
    intent: str
    content: str | None
    status: str | None
    remind_at: datetime | None
    timezone: str | None
    source: str


class PlannerClassifier(Protocol):
    async def classify(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
        context_text: str | None = None,
        prefer_rules: bool = False,
    ) -> Any: ...


class AssistantActionPlanner:
    def __init__(self, *, classifier: PlannerClassifier) -> None:
        self.classifier = classifier

    async def plan(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        turn_context: AssistantTurnContext,
    ) -> AssistantActionPlan:
        followup_plan = _plan_from_dialogue_state(command, turn_context=turn_context)
        if followup_plan is not None:
            return followup_plan

        direct_plan = _plan_with_referential_rules(command, turn_context=turn_context)
        if direct_plan is not None:
            return direct_plan

        decision = cast(
            PlannerDecision,
            await self.classifier.classify(
                command,
                conversation_id=turn_context.conversation_id,
                session_id=turn_context.session_id,
                context_text=_build_context_text(turn_context),
                prefer_rules=True,
            ),
        )
        return _normalize_decision_to_plan(decision)


def _plan_with_referential_rules(
    command: HandleInboundConversationMessageCommand,
    *,
    turn_context: AssistantTurnContext,
) -> AssistantActionPlan | None:
    if command.message_type != "text" or command.text is None:
        return None
    text = command.text.strip()
    if not text:
        return None

    normalized = text.casefold()
    object_type = _infer_object_type(text, turn_context=turn_context)

    if normalized in {"今天有什么", "我今天还有什么", "看看今天还有什么", "today"}:
        return AssistantActionPlan(
            intent="overview_show",
            action="show_overview",
            object_type=None,
            object_id=None,
            args={"view": "today"},
            confidence=0.92,
            reasoning="rules",
        )

    if normalized in _WORKING_SET_REQUESTS:
        return AssistantActionPlan(
            intent="overview_show",
            action="show_overview",
            object_type=None,
            object_id=None,
            args={"view": "working_set"},
            confidence=0.92,
            reasoning="rules",
        )

    if text.startswith("重试") and "提醒" in text:
        return AssistantActionPlan(
            intent="reminder_retry_failed",
            action="retry_failed_reminder",
            object_type="reminder",
            object_id=None,
            args={"reference_text": _strip_retry_prefix(text), "status": "failed"},
            confidence=0.9,
            reasoning="rules",
        )

    scoped_memory_plan = _plan_scoped_memory(text, turn_context=turn_context)
    if scoped_memory_plan is not None:
        return scoped_memory_plan

    direct_memory_content = _extract_prefixed_memory_content(text)
    if direct_memory_content is not None:
        return AssistantActionPlan(
            intent="memory_write",
            action="create_memory",
            object_type=None,
            object_id=None,
            args={
                "content": direct_memory_content,
                "memory_type": _infer_memory_type(direct_memory_content),
            },
            confidence=0.92,
            reasoning="rules",
        )

    if text.startswith("完成") and object_type == "task":
        reference_text = _extract_reference_after_action(text, action="完成")
        return AssistantActionPlan(
            intent="task_complete",
            action="complete_task",
            object_type="task",
            object_id=None,
            args={"reference_text": reference_text},
            confidence=0.92,
            reasoning="rules",
        )

    if ("改成待办" in text or "改成任务" in text) and object_type == "reminder":
        return AssistantActionPlan(
            intent="reminder_to_task",
            action="convert_reminder_to_task",
            object_type="reminder",
            object_id=None,
            args={"reference_text": _extract_reference_before_phrase(text, "改成")},
            confidence=0.9,
            reasoning="rules",
        )

    if "取消" in text and object_type in {"task", "reminder"}:
        action = "cancel_task" if object_type == "task" else "cancel_reminder"
        return AssistantActionPlan(
            intent=f"{object_type}_cancel",
            action=action,
            object_type=object_type,
            object_id=None,
            args={"reference_text": _extract_reference_for_cancel(text)},
            confidence=0.9 if "提醒" in text or "待办" in text or "任务" in text else 0.86,
            reasoning="rules",
        )

    if text.startswith("归档") and object_type == "memory":
        reference_text = _extract_reference_after_action(text, action="归档")
        return AssistantActionPlan(
            intent="memory_archive",
            action="archive_memory",
            object_type="memory",
            object_id=None,
            args={"reference_text": reference_text},
            confidence=0.9,
            reasoning="rules",
        )

    return None


def _plan_from_dialogue_state(
    command: HandleInboundConversationMessageCommand,
    *,
    turn_context: AssistantTurnContext,
) -> AssistantActionPlan | None:
    if command.message_type != "text" or command.text is None:
        return None
    normalized = command.text.strip()
    if not normalized or turn_context.last_assistant_action is None:
        return None

    if (
        turn_context.dialogue_mode == "confirmation"
        and normalized in _CONFIRM_YES
        and turn_context.focused_object is not None
    ):
        action = turn_context.last_assistant_action.action_type
        return AssistantActionPlan(
            intent=action,
            action=action,
            object_type=turn_context.focused_object.object_type,
            object_id=turn_context.focused_object.object_id,
            confidence=0.96,
            reasoning="rules",
        )

    if normalized in _REFERENCE_FOLLOWUPS and turn_context.visible_candidates:
        action = turn_context.last_assistant_action.action_type
        object_type = turn_context.visible_candidates[0].object_type
        return AssistantActionPlan(
            intent=action,
            action=action,
            object_type=object_type,
            object_id=None,
            args={"reference_text": _normalize_followup_reference(normalized)},
            confidence=0.94,
            reasoning="rules",
        )
    return None


def _build_context_text(turn_context: AssistantTurnContext) -> str | None:
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


def _normalize_decision_to_plan(decision: PlannerDecision) -> AssistantActionPlan:
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
                "memory_type": _infer_memory_type(decision.content),
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


def _infer_object_type(
    text: str,
    *,
    turn_context: AssistantTurnContext,
) -> str | None:
    normalized = text.casefold()
    if "提醒" in normalized:
        return "reminder"
    if "任务" in normalized or "待办" in normalized:
        return "task"
    if "记忆" in normalized:
        return "memory"
    if turn_context.focused_object is not None:
        return turn_context.focused_object.object_type
    if turn_context.visible_candidates:
        object_types = {candidate.object_type for candidate in turn_context.visible_candidates}
        if len(object_types) == 1:
            return next(iter(object_types))
    if turn_context.last_assistant_action is not None:
        if turn_context.last_assistant_action.object_type is not None:
            return turn_context.last_assistant_action.object_type
        if turn_context.last_assistant_action.action_type in {
            "list_tasks",
            "create_task",
            "complete_task",
            "cancel_task",
            "convert_reminder_to_task",
        }:
            return "task"
        if turn_context.last_assistant_action.action_type in {
            "list_reminders",
            "create_reminder",
            "cancel_reminder",
            "reschedule_reminder",
            "retry_failed_reminder",
            "convert_task_to_reminder",
        }:
            return "reminder"
        if turn_context.last_assistant_action.action_type in {
            "list_memories",
            "create_memory",
            "archive_memory",
        }:
            return "memory"
    return None


def _extract_reference_for_cancel(text: str) -> str | None:
    if "取消" not in text:
        return text
    before, _, after = text.partition("取消")
    candidate = _strip_action_noise(f"{before}{after}".strip())
    return candidate or None


def _extract_reference_after_action(text: str, *, action: str) -> str | None:
    candidate = text.removeprefix(action).strip()
    candidate = _strip_action_noise(candidate)
    return candidate or None


def _strip_action_noise(text: str) -> str:
    normalized = text
    for prefix in ("任务", "待办", "提醒", "记忆", "这条", "那个", "这个"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix).strip()
    return normalized


def _plan_scoped_memory(
    text: str,
    *,
    turn_context: AssistantTurnContext,
) -> AssistantActionPlan | None:
    scope_phrases = {
        "记到任务里": "task",
        "记到待办里": "task",
        "记到提醒里": "reminder",
    }
    for phrase, object_type in scope_phrases.items():
        if phrase not in text:
            continue
        content = _extract_scoped_memory_content(text, phrase)
        return AssistantActionPlan(
            intent="memory_write",
            action="create_memory",
            object_type=object_type,
            object_id=None,
            args={
                "content": content,
                "memory_type": _infer_memory_type(content),
                "scope_reference_text": _infer_scope_reference_text(
                    text,
                    turn_context=turn_context,
                ),
            },
            confidence=0.9,
            reasoning="rules",
        )
    return None


def _extract_prefixed_memory_content(text: str) -> str | None:
    lowered_text = text.casefold()
    for prefix in _MEMORY_PREFIXES:
        lowered_prefix = prefix.casefold()
        if lowered_text == lowered_prefix:
            return None
        if lowered_text.startswith(lowered_prefix):
            candidate = text[len(prefix) :].lstrip("：: \n\t")
            return candidate or None
    return None


def _extract_scoped_memory_content(text: str, phrase: str) -> str:
    content = text.partition(phrase)[0].strip()
    content = content.removeprefix("把").strip()
    return content or text


def _infer_scope_reference_text(
    text: str,
    *,
    turn_context: AssistantTurnContext,
) -> str | None:
    for token in ("刚才那个", "这个", "那个", "第一个", "第二个", "最后一个"):
        if token in text:
            return token
    if turn_context.focused_object is not None:
        return "这个"
    return None


def _infer_memory_type(content: str) -> str:
    normalized = content.casefold()
    if "临时" in normalized:
        return "temporary"
    if "偏好" in normalized or "喜欢" in normalized or "不喜欢" in normalized:
        return "preference"
    if "背景" in normalized:
        return "context"
    return "note"


def _strip_retry_prefix(text: str) -> str | None:
    normalized = text
    for prefix in ("重试失败提醒", "重试提醒", "重试"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix).strip()
            break
    normalized = _strip_action_noise(normalized)
    return normalized or None


def _extract_reference_before_phrase(text: str, phrase: str) -> str | None:
    before, _, _ = text.partition(phrase)
    normalized = _strip_action_noise(before.strip())
    return normalized or None


def _normalize_followup_reference(text: str) -> str:
    if text in {"另一个", "不是这个，是另一个"}:
        return "第二个"
    if text == "就刚才那个":
        return "刚才那个"
    return text
