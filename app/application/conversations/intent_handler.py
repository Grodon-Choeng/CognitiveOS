import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from app.application.audit.dto import AuditEventPageDTO
from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.conversations.kernel.facade import ConversationKernelFacade
from app.application.conversations.kernel.results import (
    AssistantConfirmationResult,
    AssistantDisambiguationResult,
    AssistantExecutionResult,
)
from app.application.memory.commands import ArchiveMemoryCommand, CreateMemoryCommand
from app.application.memory.dto import MemoryDTO, MemoryListDTO
from app.application.memory.errors import MemoryApplicationError
from app.application.memory.queries import ListMemoriesQuery
from app.application.overview.dto import OverviewDTO
from app.application.overview.queries import GetOverviewQuery
from app.application.reminders.commands import (
    CancelReminderCommand,
    CreateReminderCommand,
    RescheduleReminderCommand,
    RetryFailedReminderCommand,
)
from app.application.reminders.dto import ReminderDTO, ReminderListDTO
from app.application.reminders.errors import ReminderApplicationError
from app.application.reminders.queries import ListRemindersQuery
from app.application.tasks.commands import CancelTaskCommand, CompleteTaskCommand, CreateTaskCommand
from app.application.tasks.dto import TaskDTO, TaskListDTO
from app.application.tasks.errors import TaskApplicationError
from app.application.tasks.queries import ListTasksQuery
from app.domain.reminders.entities import ReminderStatus
from app.infrastructure.llm.gateway import LLMGateway
from app.infrastructure.llm.models import GenerateRequest
from app.observability.context import current_trace_fields

TASK_PREFIXES = ("待办", "todo", "task")
MEMORY_PREFIXES = ("记住", "记一下", "记下", "memo")
logger = logging.getLogger(__name__)


class ConversationIntent(StrEnum):
    GREETING = "greeting"
    HELP_SHOW = "help_show"
    REMINDER_CREATE = "reminder_create"
    REMINDER_CANCEL = "reminder_cancel"
    REMINDER_RESCHEDULE = "reminder_reschedule"
    REMINDER_RETRY_FAILED = "reminder_retry_failed"
    REMINDER_LIST = "reminder_list"
    TASK_CREATE = "task_create"
    TASK_CANCEL = "task_cancel"
    TASK_COMPLETE = "task_complete"
    TASK_LIST = "task_list"
    TASK_TO_REMINDER = "task_to_reminder"
    REMINDER_TO_TASK = "reminder_to_task"
    MEMORY_WRITE = "memory_write"
    MEMORY_ARCHIVE = "memory_archive"
    MEMORY_LIST = "memory_list"
    ACTIVITY_SHOW = "activity_show"
    OVERVIEW_SHOW = "overview_show"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class ConversationIntentDecision:
    intent: ConversationIntent
    content: str | None
    status: str | None
    remind_at: datetime | None
    timezone: str | None
    source: str


class TaskCreator(Protocol):
    async def create_task(self, command: CreateTaskCommand) -> TaskDTO: ...
    async def get_task(self, task_id: str) -> TaskDTO: ...

    async def complete_task(self, command: CompleteTaskCommand) -> TaskDTO: ...

    async def cancel_task(self, command: CancelTaskCommand) -> TaskDTO: ...

    async def complete_latest_task(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> TaskDTO: ...

    async def cancel_latest_task(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> TaskDTO: ...

    async def complete_matching_task(
        self,
        *,
        conversation_id: str,
        session_id: str,
        title_hint: str,
    ) -> TaskDTO: ...
    async def attach_reminder(
        self,
        *,
        task_id: str,
        reminder_id: str,
    ) -> TaskDTO: ...

    async def cancel_matching_task(
        self,
        *,
        conversation_id: str,
        session_id: str,
        title_hint: str,
    ) -> TaskDTO: ...

    async def list_tasks(self, query: ListTasksQuery) -> TaskListDTO: ...


class MemoryCreator(Protocol):
    async def create_memory(self, command: CreateMemoryCommand) -> MemoryDTO: ...

    async def archive_memory(self, command: ArchiveMemoryCommand) -> MemoryDTO: ...

    async def archive_latest_memory(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> MemoryDTO: ...

    async def archive_matching_memory(
        self,
        *,
        conversation_id: str,
        session_id: str,
        content_hint: str,
    ) -> MemoryDTO: ...

    async def list_memories(self, query: ListMemoriesQuery) -> MemoryListDTO: ...


class ReminderCreator(Protocol):
    async def create_reminder(self, command: CreateReminderCommand) -> ReminderDTO: ...
    async def get_reminder(self, reminder_id: str) -> ReminderDTO: ...

    async def cancel_reminder(self, command: CancelReminderCommand) -> ReminderDTO: ...

    async def cancel_latest_reminder(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ReminderDTO: ...

    async def cancel_matching_reminder(
        self,
        *,
        conversation_id: str,
        session_id: str,
        text_hint: str,
    ) -> ReminderDTO: ...
    async def link_task(
        self,
        *,
        reminder_id: str,
        task_id: str,
    ) -> ReminderDTO: ...
    async def retry_failed_reminder(self, command: RetryFailedReminderCommand) -> ReminderDTO: ...
    async def reschedule_reminder(self, command: RescheduleReminderCommand) -> ReminderDTO: ...

    async def list_reminders(self, query: ListRemindersQuery) -> ReminderListDTO: ...


class OverviewReader(Protocol):
    async def get_overview(self, query: GetOverviewQuery) -> OverviewDTO: ...
    async def get_today_view(self, query: GetOverviewQuery) -> OverviewDTO: ...
    async def get_working_set_view(self, query: GetOverviewQuery) -> OverviewDTO: ...


class LLMFirstConversationIntentClassifier:
    def __init__(
        self,
        *,
        llm_gateway: LLMGateway | None,
        model: str | None,
        api_key_suffix: str | None,
        provider: str = "openai",
    ) -> None:
        self.llm_gateway = llm_gateway
        self.model = model
        self.api_key_suffix = api_key_suffix
        self.provider = provider

    async def classify(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
        context_text: str | None = None,
        prefer_rules: bool = False,
    ) -> ConversationIntentDecision:
        rule_decision = _classify_with_rules(command)
        if prefer_rules and rule_decision.intent != ConversationIntent.UNKNOWN:
            return rule_decision

        llm_decision = await self._classify_with_llm(
            command=command,
            conversation_id=conversation_id,
            session_id=session_id,
            context_text=context_text,
        )
        if prefer_rules:
            if llm_decision is not None:
                return llm_decision
            return rule_decision

        if llm_decision is not None and llm_decision.intent != ConversationIntent.UNKNOWN:
            return llm_decision
        if rule_decision.intent != ConversationIntent.UNKNOWN:
            return rule_decision
        if llm_decision is not None:
            return llm_decision
        return rule_decision

    async def _classify_with_llm(
        self,
        *,
        command: HandleInboundConversationMessageCommand,
        conversation_id: str,
        session_id: str,
        context_text: str | None,
    ) -> ConversationIntentDecision | None:
        if self.llm_gateway is None or self.model is None:
            return None
        if command.message_type != "text" or command.text is None:
            return None

        try:
            trace_id, chain_id, request_id = current_trace_fields()
            result = await self.llm_gateway.generate(
                GenerateRequest(
                    prompt=_build_intent_prompt(command.text, context_text),
                    system_prompt=_build_intent_system_prompt(),
                    provider=self.provider,
                    model=self.model,
                    api_key_suffix=self.api_key_suffix,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    trace_id=trace_id,
                    chain_id=chain_id,
                    request_id=request_id,
                    metadata={"component": "conversation_intent_classifier"},
                )
            )
        except Exception as exc:
            logger.warning(
                "对话意图分类调用 LLM 失败，回退到规则分类。",
                extra={
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                },
            )
            return None

        return _parse_intent_response(result.content)


class LegacyIntentConversationHandler:
    name = "intent"

    def __init__(
        self,
        *,
        kernel_facade: ConversationKernelFacade,
    ) -> None:
        # 仅兼容旧入口的 legacy adapter。
        # 新的 conversation 能力应直接进入 kernel facade，而不是继续堆到这里。
        self.kernel_facade = kernel_facade

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult | None:
        try:
            kernel_outcome = await self.kernel_facade.handle(
                command,
                conversation_id=conversation_id,
                session_id=session_id,
            )
        except (TaskApplicationError, MemoryApplicationError, ReminderApplicationError) as exc:
            handled_by = None
            if isinstance(exc, TaskApplicationError):
                handled_by = "task"
            elif isinstance(exc, MemoryApplicationError):
                handled_by = "memory"
            elif isinstance(exc, ReminderApplicationError):
                handled_by = "reminder"
            if handled_by is None:
                raise
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by=handled_by,
                reason="legacy_kernel_feedback",
                response_text=str(exc),
            )

        execution_result = kernel_outcome.execution_result
        if execution_result is None or kernel_outcome.response_text is None:
            return None
        return ConversationInboundResult(
            handled=True,
            conversation_id=conversation_id,
            session_id=session_id,
            handled_by=kernel_outcome.handled_by,
            reason=kernel_outcome.reason,
            response_text=kernel_outcome.response_text,
        )


# Deprecated alias: 保留旧类型名供容器装配和历史调用兼容。
IntentConversationHandler = LegacyIntentConversationHandler


class _EmptyHistoryReader:
    async def list_events(
        self,
        *,
        kind: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        success: bool | None = None,
        channel: str | None = None,
        provider: str | None = None,
        tool_name: str | None = None,
        workflow_type: str | None = None,
        recorded_after: datetime | None = None,
        recorded_before: datetime | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditEventPageDTO:
        _ = (
            kind,
            conversation_id,
            session_id,
            success,
            channel,
            provider,
            tool_name,
            workflow_type,
            recorded_after,
            recorded_before,
            cursor,
            limit,
        )
        return AuditEventPageDTO(items=[])


def _classify_with_rules(
    command: HandleInboundConversationMessageCommand,
) -> ConversationIntentDecision:
    if _is_help_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.HELP_SHOW,
            content=None,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    if _is_greeting_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.GREETING,
            content=None,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    reminder_request = _extract_reminder_request(command)
    if reminder_request is not None:
        return reminder_request

    task_title = _extract_task_title(command)
    if task_title is not None:
        return ConversationIntentDecision(
            intent=ConversationIntent.TASK_CREATE,
            content=task_title,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    matched, content = _extract_action_content(
        command,
        prefixes=("完成任务", "完成待办", "done task", "complete task"),
    )
    if matched:
        return ConversationIntentDecision(
            intent=ConversationIntent.TASK_COMPLETE,
            content=content,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    task_list_status = _extract_task_list_status(command)
    if task_list_status is not None:
        return ConversationIntentDecision(
            intent=ConversationIntent.TASK_LIST,
            content=None,
            status=task_list_status,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    task_search_query = _extract_task_search_query(command)
    if task_search_query is not None:
        return ConversationIntentDecision(
            intent=ConversationIntent.TASK_LIST,
            content=task_search_query,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    matched, content = _extract_action_content(
        command,
        prefixes=("取消任务", "取消待办", "cancel task"),
    )
    if matched:
        return ConversationIntentDecision(
            intent=ConversationIntent.TASK_CANCEL,
            content=content,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    memory_content = _extract_memory_content(command)
    if memory_content is not None:
        return ConversationIntentDecision(
            intent=ConversationIntent.MEMORY_WRITE,
            content=memory_content,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    memory_search_query = _extract_memory_search_query(command)
    if memory_search_query is not None:
        return ConversationIntentDecision(
            intent=ConversationIntent.MEMORY_LIST,
            content=memory_search_query,
            status="active",
            remind_at=None,
            timezone=None,
            source="rules",
        )

    matched, content = _extract_action_content(
        command,
        prefixes=("归档记忆", "archive memory", "归档这条记忆"),
    )
    if matched:
        return ConversationIntentDecision(
            intent=ConversationIntent.MEMORY_ARCHIVE,
            content=content,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    memory_list_status = _extract_memory_list_status(command)
    if memory_list_status is not None:
        return ConversationIntentDecision(
            intent=ConversationIntent.MEMORY_LIST,
            content=None,
            status=memory_list_status,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    matched, content = _extract_action_content(
        command,
        prefixes=("取消提醒", "cancel reminder", "取消这个提醒"),
    )
    if matched:
        return ConversationIntentDecision(
            intent=ConversationIntent.REMINDER_CANCEL,
            content=content,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    matched, content = _extract_action_content(
        command,
        prefixes=("重试失败提醒", "重试提醒", "retry failed reminder", "retry reminder"),
    )
    if matched:
        return ConversationIntentDecision(
            intent=ConversationIntent.REMINDER_RETRY_FAILED,
            content=content,
            status=ReminderStatus.FAILED.value,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    reminder_list_status = _extract_reminder_list_status(command)
    if reminder_list_status is not None:
        return ConversationIntentDecision(
            intent=ConversationIntent.REMINDER_LIST,
            content=None,
            status=reminder_list_status,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    reminder_search_query = _extract_reminder_search_query(command)
    if reminder_search_query is not None:
        return ConversationIntentDecision(
            intent=ConversationIntent.REMINDER_LIST,
            content=reminder_search_query,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    if _is_overview_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.OVERVIEW_SHOW,
            content=None,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    if _is_activity_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.ACTIVITY_SHOW,
            content=None,
            status=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    return ConversationIntentDecision(
        intent=ConversationIntent.UNKNOWN,
        content=None,
        status=None,
        remind_at=None,
        timezone=None,
        source="rules",
    )


def _build_intent_system_prompt() -> str:
    return (
        "你是 CognitiveOS 的对话意图分类器。"
        "你只负责判断当前文本是否应该问候回复、展示帮助、创建 reminder、取消 reminder、创建 task、"
        "完成 task、取消 task、把 task 转成 reminder、把 reminder 转成 task、重试失败提醒、"
        "改期 reminder、写入 memory、归档 memory，或者都不是。"
        "你必须返回 JSON，格式为"
        '{"intent":"greeting|help_show|reminder_create|reminder_cancel|reminder_reschedule|reminder_retry_failed|reminder_list|task_create|task_complete|task_cancel|task_list|task_to_reminder|reminder_to_task|memory_write|memory_archive|memory_list|overview_show|activity_show|unknown",'
        '"content":"提取后的正文或 null",'
        '"status":"pending|completed|canceled|failed|active|archived|unknown|null",'
        '"remind_at":"ISO8601时间或 null","timezone":"时区或 null"}。'
        "如果文本只是打招呼，例如 hi、hello、hey、你好，返回 greeting；"
        "如果文本是在询问你能做什么、如何使用、help，返回 help_show；"
        "如果文本是在表达未来要提醒的事项，返回 reminder_create，"
        "并提取提醒正文、带时区的 ISO8601 提醒时间，以及 IANA 时区字符串；"
        "如果文本是在要求取消当前会话最近一个提醒，返回 reminder_cancel；"
        "如果文本是在要求改期某个提醒，返回 reminder_reschedule，并填写 remind_at/timezone；"
        "如果文本是在要求重试失败提醒，返回 reminder_retry_failed；"
        "如果文本是在要求查看当前会话里的提醒列表，返回 reminder_list；"
        "如果文本是在要求按关键词查找提醒，也返回 reminder_list，并把关键词写到 content；"
        "如果文本是在表达待办事项，返回 task_create；"
        "如果文本是在要求完成当前会话里最近一个待办，返回 task_complete；"
        "如果文本是在要求取消当前会话里最近一个待办，返回 task_cancel；"
        "如果文本是在要求把某个 task 转成 reminder，"
        "返回 task_to_reminder，并填写 remind_at/timezone；"
        "如果文本是在要求把某个 reminder 改成 task，返回 reminder_to_task；"
        "如果文本是在要求查看当前会话里的待办列表，返回 task_list；"
        "如果文本是在要求按关键词查找待办，也返回 task_list，并把关键词写到 content；"
        "如果文本是在要求系统记住某件事实或偏好，返回 memory_write；"
        "如果文本是在要求归档当前会话里最近一条活跃记忆，返回 memory_archive；"
        "如果文本是在要求查看当前会话里的记忆列表，返回 memory_list；"
        "如果文本是在要求按关键词查找记忆，也返回 memory_list，并把关键词写到 content；"
        "如果文本是在要求查看当前会话概览，返回 overview_show；"
        "如果文本是在要求查看当前会话最近活动，返回 activity_show；"
        "否则返回 unknown。"
    )


def _build_intent_prompt(text: str, context_text: str | None) -> str:
    if context_text:
        return f"当前会话上下文：\n{context_text}\n\n用户输入：{text}"
    return f"用户输入：{text}"


def _parse_intent_response(content: str) -> ConversationIntentDecision | None:
    try:
        parsed = json.loads(_extract_json_block(content))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None

    intent_value = parsed.get("intent")
    content_value = parsed.get("content")
    status_value = parsed.get("status")
    remind_at_value = parsed.get("remind_at")
    timezone_value = parsed.get("timezone")
    if not isinstance(intent_value, str):
        return None

    try:
        intent = ConversationIntent(intent_value)
    except ValueError:
        return None

    normalized_content = content_value if isinstance(content_value, str) else None
    if normalized_content is not None:
        normalized_content = normalized_content.strip() or None
    normalized_status = status_value if isinstance(status_value, str) else None
    if normalized_status is not None:
        normalized_status = normalized_status.strip() or None
    remind_at: datetime | None = None
    timezone: str | None = timezone_value if isinstance(timezone_value, str) else None
    if timezone is not None:
        timezone = timezone.strip() or None
    if intent == ConversationIntent.REMINDER_CREATE:
        if normalized_content is None or not isinstance(remind_at_value, str) or timezone is None:
            return None
        try:
            remind_at = datetime.fromisoformat(remind_at_value)
        except ValueError:
            return None
    elif intent in {ConversationIntent.TASK_CREATE, ConversationIntent.MEMORY_WRITE}:
        if normalized_content is None:
            return None
    elif intent in {
        ConversationIntent.REMINDER_RESCHEDULE,
        ConversationIntent.TASK_TO_REMINDER,
    }:
        if not isinstance(remind_at_value, str) or timezone is None:
            return None
        try:
            remind_at = datetime.fromisoformat(remind_at_value)
        except ValueError:
            return None
    elif intent not in {
        ConversationIntent.GREETING,
        ConversationIntent.HELP_SHOW,
        ConversationIntent.UNKNOWN,
        ConversationIntent.REMINDER_CANCEL,
        ConversationIntent.REMINDER_RETRY_FAILED,
        ConversationIntent.REMINDER_LIST,
        ConversationIntent.REMINDER_TO_TASK,
        ConversationIntent.TASK_COMPLETE,
        ConversationIntent.TASK_CANCEL,
        ConversationIntent.TASK_LIST,
        ConversationIntent.MEMORY_ARCHIVE,
        ConversationIntent.MEMORY_LIST,
        ConversationIntent.ACTIVITY_SHOW,
        ConversationIntent.OVERVIEW_SHOW,
    }:
        return None
    return ConversationIntentDecision(
        intent=intent,
        content=normalized_content,
        status=normalized_status,
        remind_at=remind_at,
        timezone=timezone,
        source="llm",
    )


def _extract_json_block(content: str) -> str:
    normalized = content.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return normalized


def _extract_reminder_request(
    command: HandleInboundConversationMessageCommand,
) -> ConversationIntentDecision | None:
    if command.message_type != "text" or command.text is None:
        return None

    normalized_text = command.text.strip()
    if not normalized_text:
        return None

    for prefix in ("提醒", "remind"):
        if not normalized_text.casefold().startswith(prefix.casefold()):
            continue
        candidate = normalized_text[len(prefix) :].lstrip("：: \n\t")
        if not candidate:
            return None
        parts = candidate.split(maxsplit=1)
        if len(parts) != 2:
            continue
        remind_at_text, reminder_content = parts
        try:
            remind_at = datetime.fromisoformat(remind_at_text)
        except ValueError:
            continue
        timezone = str(remind_at.tzinfo) if remind_at.tzinfo is not None else None
        if timezone is None:
            continue
        reminder_content = reminder_content.strip()
        if not reminder_content:
            continue
        return ConversationIntentDecision(
            intent=ConversationIntent.REMINDER_CREATE,
            content=reminder_content,
            status=None,
            remind_at=remind_at,
            timezone=timezone,
            source="rules",
        )

    return None


def _is_overview_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {"查看概览", "看看概览", "今天有什么", "show overview", "overview"}


def _is_help_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {
        "help",
        "帮助",
        "你可以帮我做什么",
        "你能做什么",
        "你会什么",
        "可以做什么",
        "怎么用",
        "你可以做什么",
    }


def _is_greeting_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {
        "hi",
        "hello",
        "hey",
        "你好",
        "嗨",
        "哈喽",
        "在吗",
    }


def _is_activity_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {"查看最近活动", "最近活动", "activity", "show activity"}


def _format_overview_text(overview: OverviewDTO) -> str:
    lines = ["当前概览："]

    if overview.pending_reminders:
        lines.append("待办提醒：")
        for reminder in overview.pending_reminders:
            lines.append(f"- {reminder.text} @ {reminder.remind_at.isoformat()}")
    else:
        lines.append("待办提醒：无")

    if overview.pending_tasks:
        lines.append("待办任务：")
        for task in overview.pending_tasks:
            lines.append(f"- {task.title}")
    else:
        lines.append("待办任务：无")

    if overview.active_memories:
        lines.append("活跃记忆：")
        for memory in overview.active_memories:
            lines.append(f"- {memory.content}")
    else:
        lines.append("活跃记忆：无")

    if overview.recent_activity:
        lines.append("最近活动：")
        for event in overview.recent_activity:
            lines.append(f"- [{event.kind}] {event.summary}")

    return "\n".join(lines)


def _format_recent_activity_text(overview: OverviewDTO) -> str:
    if not overview.recent_activity:
        return "当前没有最近活动。"
    lines = ["最近活动："]
    for event in overview.recent_activity:
        lines.append(f"- [{event.kind}] {event.summary}")
    return "\n".join(lines)


def _format_overview_context_hint(overview: OverviewDTO) -> str:
    lines = []
    if overview.pending_reminders:
        lines.append("pending_reminders:")
        for reminder in overview.pending_reminders:
            lines.append(f"- {reminder.text}")
    if overview.pending_tasks:
        lines.append("pending_tasks:")
        for task in overview.pending_tasks:
            lines.append(f"- {task.title}")
    if overview.active_memories:
        lines.append("active_memories:")
        for memory in overview.active_memories:
            lines.append(f"- {memory.content}")
    if overview.recent_activity:
        lines.append("recent_activity:")
        for event in overview.recent_activity:
            lines.append(f"- [{event.kind}] {event.summary}")
    return "\n".join(lines) if lines else "当前会话暂无上下文。"


def _format_task_list_text(
    task_list: TaskListDTO,
    status: str | None,
    query: str | None,
) -> str:
    title = _build_filtered_title("任务", status, query)
    if not task_list.items:
        return f"当前没有{title}。"
    lines = [f"当前{title}："]
    for task in task_list.items:
        lines.append(f"- [{task.status}] {task.title}")
    return "\n".join(lines)


def _format_reminder_list_text(
    reminder_list: ReminderListDTO,
    status: str | None,
    query: str | None,
) -> str:
    title = _build_filtered_title("提醒", status, query)
    if not reminder_list.items:
        return f"当前没有{title}。"
    lines = [f"当前{title}："]
    for reminder in reminder_list.items:
        lines.append(f"- [{reminder.status}] {reminder.text} @ {reminder.remind_at.isoformat()}")
    return "\n".join(lines)


def _format_memory_list_text(memory_list: MemoryListDTO, status: str | None) -> str:
    title = _build_status_title("记忆", status)
    if not memory_list.items:
        return f"当前没有{title}。"
    lines = [f"当前{title}："]
    for memory in memory_list.items:
        lines.append(f"- [{memory.status}] {memory.content}")
    return "\n".join(lines)


def _extract_action_content(
    command: HandleInboundConversationMessageCommand,
    *,
    prefixes: tuple[str, ...],
) -> tuple[bool, str | None]:
    if command.message_type != "text" or command.text is None:
        return False, None
    normalized_text = command.text.strip()
    lowered_text = normalized_text.casefold()
    for prefix in prefixes:
        lowered_prefix = prefix.casefold()
        if lowered_text == lowered_prefix:
            return True, None
        if lowered_text.startswith(lowered_prefix):
            content = normalized_text[len(prefix) :].lstrip("：: \n\t")
            return True, content or None
    return False, None


def _extract_task_title(command: HandleInboundConversationMessageCommand) -> str | None:
    return _extract_prefixed_content(command, prefixes=TASK_PREFIXES)


def _extract_memory_content(command: HandleInboundConversationMessageCommand) -> str | None:
    return _extract_prefixed_content(command, prefixes=MEMORY_PREFIXES)


def _extract_prefixed_content(
    command: HandleInboundConversationMessageCommand,
    *,
    prefixes: tuple[str, ...],
) -> str | None:
    if command.message_type != "text" or command.text is None:
        return None

    normalized_text = command.text.strip()
    if not normalized_text:
        return None

    lowered_text = normalized_text.casefold()
    for prefix in prefixes:
        lowered_prefix = prefix.casefold()
        if lowered_text == lowered_prefix:
            return None
        if lowered_text.startswith(lowered_prefix):
            candidate = normalized_text[len(prefix) :].lstrip("：: \n\t")
            if candidate:
                return candidate
    return None


def _extract_task_list_status(command: HandleInboundConversationMessageCommand) -> str | None:
    if command.message_type != "text" or command.text is None:
        return None
    normalized = command.text.strip().casefold()
    mapping = {
        "查看待办": "pending",
        "查看任务": None,
        "查看已完成任务": "completed",
        "查看已取消任务": "canceled",
        "task list": None,
        "show tasks": None,
    }
    return mapping.get(normalized)


def _extract_memory_list_status(command: HandleInboundConversationMessageCommand) -> str | None:
    if command.message_type != "text" or command.text is None:
        return None
    normalized = command.text.strip().casefold()
    mapping = {
        "查看记忆": "active",
        "查看记忆列表": "active",
        "查看已归档记忆": "archived",
        "memory list": "active",
        "show memories": "active",
    }
    return mapping.get(normalized)


def _extract_memory_search_query(
    command: HandleInboundConversationMessageCommand,
) -> str | None:
    matched, content = _extract_action_content(
        command,
        prefixes=("搜索记忆", "查找记忆", "search memory", "find memory"),
    )
    if not matched:
        return None
    return content


def _extract_task_search_query(
    command: HandleInboundConversationMessageCommand,
) -> str | None:
    matched, content = _extract_action_content(
        command,
        prefixes=("搜索任务", "查找任务", "search task", "find task"),
    )
    if not matched:
        return None
    return content


def _extract_reminder_list_status(command: HandleInboundConversationMessageCommand) -> str | None:
    if command.message_type != "text" or command.text is None:
        return None
    normalized = command.text.strip().casefold()
    mapping = {
        "查看提醒": None,
        "查看提醒列表": None,
        "查看已取消提醒": "canceled",
        "查看已完成提醒": "completed",
        "查看失败提醒": "failed",
        "查看已失败提醒": "failed",
        "reminder list": None,
        "show reminders": None,
    }
    return mapping.get(normalized)


def _extract_reminder_search_query(
    command: HandleInboundConversationMessageCommand,
) -> str | None:
    matched, content = _extract_action_content(
        command,
        prefixes=("搜索提醒", "查找提醒", "search reminder", "find reminder"),
    )
    if not matched:
        return None
    return content


def _build_status_title(noun: str, status: str | None) -> str:
    if status == "pending":
        return f"待办{noun}"
    if status == "completed":
        return f"已完成{noun}"
    if status == "canceled":
        return f"已取消{noun}"
    if status == "failed":
        return f"失败{noun}"
    if status == "archived":
        return f"已归档{noun}"
    if status == "active":
        return f"活跃{noun}"
    return noun


def _build_filtered_title(noun: str, status: str | None, query: str | None) -> str:
    title = _build_status_title(noun, status)
    if query is None:
        return title
    return f"匹配“{query}”的{title}"


def _handled_by_for_intent(intent: ConversationIntent) -> str | None:
    if intent in {
        ConversationIntent.REMINDER_CREATE,
        ConversationIntent.REMINDER_CANCEL,
        ConversationIntent.REMINDER_LIST,
    }:
        return "reminder"
    if intent in {
        ConversationIntent.TASK_CREATE,
        ConversationIntent.TASK_CANCEL,
        ConversationIntent.TASK_COMPLETE,
        ConversationIntent.TASK_LIST,
    }:
        return "task"
    if intent in {
        ConversationIntent.MEMORY_WRITE,
        ConversationIntent.MEMORY_ARCHIVE,
        ConversationIntent.MEMORY_LIST,
    }:
        return "memory"
    if intent == ConversationIntent.OVERVIEW_SHOW:
        return "overview"
    return None


def _handled_by_for_action(action: str | None) -> str | None:
    if action in {
        "create_task",
        "list_tasks",
        "complete_task",
        "cancel_task",
        "convert_reminder_to_task",
    }:
        return "task"
    if action in {
        "create_reminder",
        "list_reminders",
        "cancel_reminder",
        "reschedule_reminder",
        "retry_failed_reminder",
        "convert_task_to_reminder",
    }:
        return "reminder"
    if action in {"create_memory", "list_memories", "archive_memory"}:
        return "memory"
    if action in {"show_overview", "show_activity"}:
        return "overview"
    if action in {"reply_greeting", "show_help"}:
        return "conversation"
    return None


def _reason_for_result(
    intent: str,
    action: str | None,
    reasoning: str | None,
    result: AssistantExecutionResult | AssistantDisambiguationResult | AssistantConfirmationResult,
) -> str:
    source = reasoning if reasoning in {"rules", "llm"} else "kernel"
    if isinstance(result, AssistantDisambiguationResult):
        return f"{action or 'conversation'}_needs_disambiguation"
    if isinstance(result, AssistantConfirmationResult):
        return f"{action or 'conversation'}_needs_confirmation"
    if not result.success:
        return f"{intent}_feedback"
    action_reason_map = {
        "reply_greeting": f"greeting_replied_via_{source}",
        "show_help": f"help_shown_via_{source}",
        "create_task": f"task_created_via_{source}",
        "list_tasks": f"task_listed_via_{source}",
        "complete_task": f"task_completed_via_{source}",
        "cancel_task": f"task_canceled_via_{source}",
        "create_reminder": f"reminder_created_via_{source}",
        "cancel_reminder": f"reminder_canceled_via_{source}",
        "reschedule_reminder": f"reminder_rescheduled_via_{source}",
        "retry_failed_reminder": f"reminder_retried_via_{source}",
        "list_reminders": f"reminder_listed_via_{source}",
        "convert_task_to_reminder": f"task_converted_to_reminder_via_{source}",
        "convert_reminder_to_task": f"reminder_converted_to_task_via_{source}",
        "create_memory": f"memory_created_via_{source}",
        "archive_memory": f"memory_archived_via_{source}",
        "list_memories": f"memory_listed_via_{source}",
        "show_overview": f"overview_shown_via_{source}",
        "show_activity": f"activity_shown_via_{source}",
    }
    return action_reason_map.get(result.action, f"{intent}_handled")
