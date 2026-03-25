import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

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
_DAY_OFFSETS = {
    "今天": 0,
    "明天": 1,
    "后天": 2,
}
_PERIOD_DEFAULT_HOUR = {
    "早上": 9,
    "上午": 9,
    "中午": 12,
    "下午": 15,
    "晚上": 20,
}
_CHINESE_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
_TIME_RE = re.compile(
    r"(?P<hour>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})点"
    r"(?:(?P<minute>\d{1,2}|[零〇一二两三四五六七八九十]{1,3})分?)?"
)


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
    def __init__(
        self,
        *,
        classifier: PlannerClassifier,
        now_provider: Callable[[], datetime] | None = None,
        default_timezone: str = "Asia/Shanghai",
    ) -> None:
        self.classifier = classifier
        self.now_provider = now_provider or _default_now
        self.default_timezone = default_timezone

    async def plan(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        turn_context: AssistantTurnContext,
    ) -> AssistantActionPlan:
        followup_plan = _plan_from_dialogue_state(command, turn_context=turn_context)
        if followup_plan is not None:
            return followup_plan

        direct_plan = _plan_with_referential_rules(
            command,
            turn_context=turn_context,
            now_provider=self.now_provider,
            default_timezone=self.default_timezone,
        )
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
    now_provider: Callable[[], datetime],
    default_timezone: str,
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

    reminder_create_plan = _plan_natural_reminder_creation(
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
            args={"reference_text": _strip_retry_prefix(text), "status": "failed"},
            confidence=0.9,
            reasoning="rules",
        )

    task_to_reminder_plan = _plan_task_to_reminder(
        text,
        object_type=object_type,
        now_provider=now_provider,
        default_timezone=default_timezone,
    )
    if task_to_reminder_plan is not None:
        return task_to_reminder_plan

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

    reminder_reschedule_plan = _plan_reminder_reschedule(
        text,
        object_type=object_type,
        now_provider=now_provider,
        default_timezone=default_timezone,
    )
    if reminder_reschedule_plan is not None:
        return reminder_reschedule_plan

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
    turn_context: AssistantTurnContext | None,
) -> str | None:
    for token in ("刚才那个", "这个", "那个", "第一个", "第二个", "最后一个"):
        if token in text:
            return token
    if turn_context is not None and turn_context.focused_object is not None:
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


def _plan_natural_reminder_creation(
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
    schedule = _parse_natural_schedule(
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


def _plan_task_to_reminder(
    text: str,
    *,
    object_type: str | None,
    now_provider: Callable[[], datetime],
    default_timezone: str,
) -> AssistantActionPlan | None:
    if object_type != "task" or "提醒我" not in text:
        return None
    schedule = _parse_natural_schedule(
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
            "reference_text": _infer_scope_reference_text(text, turn_context=None),
            "remind_at": remind_at,
            "timezone": timezone,
        },
        confidence=0.9,
        reasoning="rules",
    )


def _plan_reminder_reschedule(
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
    schedule = _parse_natural_schedule(
        normalized_target_text,
        now_provider=now_provider,
        default_timezone=default_timezone,
    )
    args = {"reference_text": _infer_scope_reference_text(text, turn_context=None)}
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


def _parse_natural_schedule(
    text: str,
    *,
    now_provider: Callable[[], datetime],
    default_timezone: str,
) -> tuple[datetime, str] | None:
    normalized = _normalize_time_text(text)
    day_offset = _extract_day_offset(normalized)
    period = _extract_period(normalized)
    hour, minute = _extract_hour_minute(normalized)
    if day_offset is None and period is None and hour is None:
        return None

    timezone = ZoneInfo(default_timezone)
    current_time = now_provider().astimezone(timezone)
    target_date = (current_time + timedelta(days=day_offset or 0)).date()

    if hour is None:
        hour = _PERIOD_DEFAULT_HOUR.get(period or "", 9)
    if minute is None:
        minute = 0
    if period in {"下午", "晚上"} and hour < 12:
        hour += 12
    if period == "中午" and hour < 11:
        hour += 12

    remind_at = datetime(
        target_date.year,
        target_date.month,
        target_date.day,
        hour,
        minute,
        tzinfo=timezone,
    )
    return remind_at, default_timezone


def _normalize_time_text(text: str) -> str:
    normalized = text.strip()
    normalized = normalized.replace("明早", "明天早上")
    normalized = normalized.replace("今早", "今天早上")
    normalized = normalized.replace("今晚", "今天晚上")
    return normalized


def _extract_day_offset(text: str) -> int | None:
    for token, offset in _DAY_OFFSETS.items():
        if token in text:
            return offset
    return 0 if any(token in text for token in _PERIOD_DEFAULT_HOUR) else None


def _extract_period(text: str) -> str | None:
    for token in _PERIOD_DEFAULT_HOUR:
        if token in text:
            return token
    return None


def _extract_hour_minute(text: str) -> tuple[int | None, int | None]:
    matched = _TIME_RE.search(text)
    if matched is None:
        return None, None
    hour = _parse_chinese_number(matched.group("hour"))
    minute_text = matched.group("minute")
    minute = _parse_chinese_number(minute_text) if minute_text else 0
    return hour, minute


def _parse_chinese_number(value: str | None) -> int | None:
    if value is None:
        return None
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if value.startswith("十"):
        return 10 + _CHINESE_DIGITS.get(value[1], 0)
    if value.endswith("十"):
        return _CHINESE_DIGITS.get(value[0], 0) * 10
    if "十" in value and len(value) == 3:
        return _CHINESE_DIGITS.get(value[0], 0) * 10 + _CHINESE_DIGITS.get(value[2], 0)
    if len(value) == 1:
        return _CHINESE_DIGITS.get(value)
    return None


def _default_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


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
