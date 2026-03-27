from collections.abc import Callable
from datetime import datetime

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.state import AssistantTurnContext
from app.application.conversations.kernel.temporal_parsing import parse_natural_schedule

_MEMORY_PREFIXES = ("记住", "记一下", "记下", "memo")
_WORKING_SET_REQUESTS = {
    "这会话里最近在处理什么",
    "最近在处理什么",
    "当前工作集",
    "working set",
}
_CANCEL_ALL_REMINDER_HINTS = ("所有提醒", "全部提醒", "所有的提醒", "全部的提醒")
_ACKNOWLEDGE_REMINDER_HINTS = ("已经提醒过", "提醒过了", "已提醒过")


def plan_with_referential_rules(
    command: HandleInboundConversationMessageCommand,
    *,
    turn_context: AssistantTurnContext,
    now_provider: Callable[[], datetime],
    default_timezone: str,
) -> AssistantActionPlan | None:
    if command.message_type != "text" or command.text is None:
        return None
    text = command.text.strip()
    if not text:
        return None

    normalized = text.casefold()
    object_type = infer_object_type(text, turn_context=turn_context)

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

    reminder_create_plan = plan_natural_reminder_creation(
        text,
        now_provider=now_provider,
        default_timezone=default_timezone,
    )
    if reminder_create_plan is not None and object_type != "task":
        return reminder_create_plan

    if text.startswith("重试") and "提醒" in text:
        return AssistantActionPlan(
            intent="reminder_retry_failed",
            action="retry_failed_reminder",
            object_type="reminder",
            object_id=None,
            args={"reference_text": strip_retry_prefix(text), "status": "failed"},
            confidence=0.9,
            reasoning="rules",
        )

    task_to_reminder_plan = plan_task_to_reminder(
        text,
        object_type=object_type,
        now_provider=now_provider,
        default_timezone=default_timezone,
    )
    if task_to_reminder_plan is not None:
        return task_to_reminder_plan

    if text.startswith("完成") and object_type == "task":
        reference_text = extract_reference_after_action(text, action="完成")
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
            args={"reference_text": extract_reference_before_phrase(text, "改成")},
            confidence=0.9,
            reasoning="rules",
        )

    reminder_acknowledgement_plan = plan_reminder_acknowledgement(
        text,
        object_type=object_type,
    )
    if reminder_acknowledgement_plan is not None:
        return reminder_acknowledgement_plan

    reminder_reschedule_plan = plan_reminder_reschedule(
        text,
        object_type=object_type,
        now_provider=now_provider,
        default_timezone=default_timezone,
    )
    if reminder_reschedule_plan is not None:
        return reminder_reschedule_plan

    scoped_memory_plan = plan_scoped_memory(text, turn_context=turn_context)
    if scoped_memory_plan is not None:
        return scoped_memory_plan

    direct_memory_content = extract_prefixed_memory_content(text)
    if direct_memory_content is not None:
        return AssistantActionPlan(
            intent="memory_write",
            action="create_memory",
            object_type=None,
            object_id=None,
            args={
                "content": direct_memory_content,
                "memory_type": infer_memory_type(direct_memory_content),
            },
            confidence=0.92,
            reasoning="rules",
        )

    if "取消" in text and object_type in {"task", "reminder"}:
        if object_type == "reminder" and _is_cancel_all_reminders_request(text):
            return AssistantActionPlan(
                intent="reminder_cancel_all",
                action="cancel_all_reminders",
                object_type=None,
                object_id=None,
                confidence=0.94,
                reasoning="rules",
            )
        action = "cancel_task" if object_type == "task" else "cancel_reminder"
        return AssistantActionPlan(
            intent=f"{object_type}_cancel",
            action=action,
            object_type=object_type,
            object_id=None,
            args={"reference_text": extract_reference_for_cancel(text)},
            confidence=0.9 if "提醒" in text or "待办" in text or "任务" in text else 0.86,
            reasoning="rules",
        )

    if text.startswith("归档") and object_type == "memory":
        reference_text = extract_reference_after_action(text, action="归档")
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


def infer_object_type(
    text: str,
    *,
    turn_context: AssistantTurnContext,
) -> str | None:
    normalized = text.casefold()
    if "任务" in normalized or "待办" in normalized:
        return "task"
    if "提醒" in normalized:
        return "reminder"
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
            "cancel_all_reminders",
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


def extract_reference_for_cancel(text: str) -> str | None:
    if "取消" not in text:
        return text
    before, _, after = text.partition("取消")
    candidate = strip_action_noise(f"{before}{after}".strip())
    return candidate or None


def extract_reference_after_action(text: str, *, action: str) -> str | None:
    candidate = text.removeprefix(action).strip()
    candidate = strip_action_noise(candidate)
    return candidate or None


def strip_action_noise(text: str) -> str:
    normalized = text
    changed = True
    while changed:
        changed = False
        for prefix in ("任务", "待办", "提醒", "记忆", "这条", "那个", "这个"):
            if normalized.startswith(prefix):
                normalized = normalized.removeprefix(prefix).strip()
                changed = True
    return normalized


def _is_cancel_all_reminders_request(text: str) -> bool:
    normalized = text.replace(" ", "")
    if "取消" not in normalized:
        return False
    if any(hint in normalized for hint in _CANCEL_ALL_REMINDER_HINTS):
        return True
    return "所有" in normalized and "提醒" in normalized


def plan_scoped_memory(
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
        content = extract_scoped_memory_content(text, phrase)
        return AssistantActionPlan(
            intent="memory_write",
            action="create_memory",
            object_type=object_type,
            object_id=None,
            args={
                "content": content,
                "memory_type": infer_memory_type(content),
                "scope_reference_text": infer_scope_reference_text(
                    text,
                    turn_context=turn_context,
                ),
            },
            confidence=0.9,
            reasoning="rules",
        )
    return None


def extract_prefixed_memory_content(text: str) -> str | None:
    lowered_text = text.casefold()
    for prefix in _MEMORY_PREFIXES:
        lowered_prefix = prefix.casefold()
        if lowered_text == lowered_prefix:
            return None
        if lowered_text.startswith(lowered_prefix):
            candidate = text[len(prefix) :].lstrip("：: \n\t")
            return candidate or None
    return None


def extract_scoped_memory_content(text: str, phrase: str) -> str:
    content = text.partition(phrase)[0].strip()
    content = content.removeprefix("把").strip()
    return content or text


def infer_scope_reference_text(
    text: str,
    *,
    turn_context: AssistantTurnContext | None,
) -> str | None:
    for token in (
        "倒数第二个",
        "刚才那个",
        "这个",
        "那个",
        "第一个",
        "第二个",
        "第三个",
        "最后一个",
        "上一个",
        "前一个",
    ):
        if token in text:
            return token
    if turn_context is not None and turn_context.focused_object is not None:
        return "这个"
    return None


def infer_memory_type(content: str) -> str:
    normalized = content.casefold()
    if "临时" in normalized:
        return "temporary"
    if "偏好" in normalized or "喜欢" in normalized or "不喜欢" in normalized:
        return "preference"
    if "背景" in normalized:
        return "context"
    return "note"


def plan_natural_reminder_creation(
    text: str,
    *,
    now_provider: Callable[[], datetime],
    default_timezone: str,
) -> AssistantActionPlan | None:
    time_text, separator, content = text.partition("提醒我")
    if not separator:
        return None
    normalized_content = content.strip()
    if not normalized_content:
        return None
    schedule = parse_natural_schedule(
        time_text,
        now_provider=now_provider,
        default_timezone=default_timezone,
    )
    if schedule is None:
        return None
    remind_at, timezone = schedule
    return AssistantActionPlan(
        intent="reminder_create",
        action="create_reminder",
        object_type="reminder",
        object_id=None,
        args={
            "text": normalized_content,
            "remind_at": remind_at,
            "timezone": timezone,
        },
        confidence=0.91,
        reasoning="rules",
    )


def plan_task_to_reminder(
    text: str,
    *,
    object_type: str | None,
    now_provider: Callable[[], datetime],
    default_timezone: str,
) -> AssistantActionPlan | None:
    if object_type != "task" or "提醒我" not in text:
        return None
    schedule = parse_natural_schedule(
        text,
        now_provider=now_provider,
        default_timezone=default_timezone,
    )
    if schedule is None:
        return None
    remind_at, timezone = schedule
    return AssistantActionPlan(
        intent="task_to_reminder",
        action="convert_task_to_reminder",
        object_type="task",
        object_id=None,
        args={
            "reference_text": infer_scope_reference_text(text, turn_context=None),
            "remind_at": remind_at,
            "timezone": timezone,
        },
        confidence=0.9,
        reasoning="rules",
    )


def plan_reminder_reschedule(
    text: str,
    *,
    object_type: str | None,
    now_provider: Callable[[], datetime],
    default_timezone: str,
) -> AssistantActionPlan | None:
    if object_type != "reminder":
        return None
    if "改到" in text:
        _, _, target_text = text.partition("改到")
    elif "改成" in text:
        _, _, target_text = text.partition("改成")
    elif "改为" in text:
        _, _, target_text = text.partition("改为")
    else:
        return None
    normalized_target_text = target_text.strip()
    if not normalized_target_text:
        return None
    schedule = parse_natural_schedule(
        normalized_target_text,
        now_provider=now_provider,
        default_timezone=default_timezone,
    )
    args = {"reference_text": infer_scope_reference_text(text, turn_context=None)}
    if schedule is None:
        args["text"] = normalized_target_text
    else:
        remind_at, timezone = schedule
        args["remind_at"] = remind_at
        args["timezone"] = timezone
    return AssistantActionPlan(
        intent="reminder_reschedule",
        action="reschedule_reminder",
        object_type="reminder",
        object_id=None,
        args=args,
        confidence=0.9,
        reasoning="rules",
    )


def plan_reminder_acknowledgement(
    text: str,
    *,
    object_type: str | None,
) -> AssistantActionPlan | None:
    if object_type != "reminder":
        return None
    if not any(hint in text for hint in _ACKNOWLEDGE_REMINDER_HINTS):
        return None
    return AssistantActionPlan(
        intent="reminder_acknowledge",
        action="acknowledge_reminder",
        object_type="reminder",
        object_id=None,
        args={
            "reference_text": extract_reference_before_any_phrase(
                text,
                _ACKNOWLEDGE_REMINDER_HINTS,
            )
        },
        confidence=0.9,
        reasoning="rules",
    )


def strip_retry_prefix(text: str) -> str | None:
    normalized = text
    for prefix in ("重试失败提醒", "重试提醒", "重试"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix).strip()
            break
    normalized = strip_action_noise(normalized)
    return normalized or None


def extract_reference_before_phrase(text: str, phrase: str) -> str | None:
    before, _, _ = text.partition(phrase)
    normalized = strip_action_noise(before.strip())
    return normalized or None


def extract_reference_before_any_phrase(text: str, phrases: tuple[str, ...]) -> str | None:
    for phrase in phrases:
        if phrase in text:
            return extract_reference_before_phrase(text, phrase)
    return None
