import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.memory.commands import CreateMemoryCommand
from app.application.memory.conversation_handler import _extract_memory_content
from app.application.memory.dto import MemoryDTO, MemoryListDTO
from app.application.memory.queries import ListMemoriesQuery
from app.application.overview.dto import OverviewDTO
from app.application.overview.queries import GetOverviewQuery
from app.application.reminders.commands import CreateReminderCommand
from app.application.reminders.dto import ReminderDTO, ReminderListDTO
from app.application.reminders.queries import ListRemindersQuery
from app.application.tasks.commands import CreateTaskCommand
from app.application.tasks.conversation_handler import _extract_task_title
from app.application.tasks.dto import TaskDTO, TaskListDTO
from app.application.tasks.queries import ListTasksQuery
from app.infrastructure.llm.gateway import LLMGateway
from app.infrastructure.llm.models import GenerateRequest


class ConversationIntent(StrEnum):
    REMINDER_CREATE = "reminder_create"
    REMINDER_CANCEL = "reminder_cancel"
    REMINDER_LIST = "reminder_list"
    TASK_CREATE = "task_create"
    TASK_CANCEL = "task_cancel"
    TASK_COMPLETE = "task_complete"
    TASK_LIST = "task_list"
    MEMORY_WRITE = "memory_write"
    MEMORY_ARCHIVE = "memory_archive"
    MEMORY_LIST = "memory_list"
    OVERVIEW_SHOW = "overview_show"
    UNKNOWN = "unknown"


@dataclass(slots=True, frozen=True)
class ConversationIntentDecision:
    intent: ConversationIntent
    content: str | None
    remind_at: datetime | None
    timezone: str | None
    source: str


class TaskCreator(Protocol):
    async def create_task(self, command: CreateTaskCommand) -> TaskDTO: ...

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

    async def list_tasks(self, query: ListTasksQuery) -> TaskListDTO: ...


class MemoryCreator(Protocol):
    async def create_memory(self, command: CreateMemoryCommand) -> MemoryDTO: ...

    async def archive_latest_memory(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> MemoryDTO: ...

    async def list_memories(self, query: ListMemoriesQuery) -> MemoryListDTO: ...


class ReminderCreator(Protocol):
    async def create_reminder(self, command: CreateReminderCommand) -> ReminderDTO: ...

    async def cancel_latest_reminder(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ReminderDTO: ...

    async def list_reminders(self, query: ListRemindersQuery) -> ReminderListDTO: ...


class OverviewReader(Protocol):
    async def get_overview(self, query: GetOverviewQuery) -> OverviewDTO: ...


class LLMFirstConversationIntentClassifier:
    def __init__(
        self,
        *,
        llm_gateway: LLMGateway | None,
        model: str | None,
        api_key_suffix: str | None,
    ) -> None:
        self.llm_gateway = llm_gateway
        self.model = model
        self.api_key_suffix = api_key_suffix

    async def classify(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationIntentDecision:
        llm_decision = await self._classify_with_llm(
            command=command,
            conversation_id=conversation_id,
            session_id=session_id,
        )
        if llm_decision is not None and llm_decision.intent != ConversationIntent.UNKNOWN:
            return llm_decision
        rule_decision = _classify_with_rules(command)
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
    ) -> ConversationIntentDecision | None:
        if self.llm_gateway is None or self.model is None:
            return None
        if command.message_type != "text" or command.text is None:
            return None

        try:
            result = await self.llm_gateway.generate(
                GenerateRequest(
                    prompt=_build_intent_prompt(command.text),
                    system_prompt=_build_intent_system_prompt(),
                    provider="openai",
                    model=self.model,
                    api_key_suffix=self.api_key_suffix,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    metadata={"component": "conversation_intent_classifier"},
                )
            )
        except Exception:
            return None

        return _parse_intent_response(result.content)


class IntentConversationHandler:
    name = "intent"

    def __init__(
        self,
        *,
        classifier: LLMFirstConversationIntentClassifier,
        task_service: TaskCreator,
        memory_service: MemoryCreator,
        reminder_service: ReminderCreator,
        overview_service: OverviewReader,
    ) -> None:
        self.classifier = classifier
        self.task_service = task_service
        self.memory_service = memory_service
        self.reminder_service = reminder_service
        self.overview_service = overview_service

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult | None:
        decision = await self.classifier.classify(
            command,
            conversation_id=conversation_id,
            session_id=session_id,
        )
        if decision.intent == ConversationIntent.TASK_CREATE and decision.content is not None:
            await self.task_service.create_task(
                CreateTaskCommand(
                    title=decision.content,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    source_channel=command.channel,
                    source_user_id=command.user_identity,
                    source_chat_id=command.chat_id,
                    source_thread_id=command.thread_id,
                )
            )
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by="task",
                reason=f"task_created_via_{decision.source}",
                response_text=f"好的，已创建待办：{decision.content}",
            )
        if decision.intent == ConversationIntent.TASK_LIST:
            task_list = await self.task_service.list_tasks(
                ListTasksQuery(
                    conversation_id=conversation_id,
                    session_id=session_id,
                    limit=5,
                )
            )
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by="task",
                reason=f"task_listed_via_{decision.source}",
                response_text=_format_task_list_text(task_list),
            )
        if decision.intent == ConversationIntent.TASK_COMPLETE:
            await self.task_service.complete_latest_task(
                conversation_id=conversation_id,
                session_id=session_id,
            )
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by="task",
                reason=f"task_completed_via_{decision.source}",
                response_text="好的，已完成最近一条待办。",
            )
        if (
            decision.intent == ConversationIntent.REMINDER_CREATE
            and decision.content is not None
            and decision.remind_at is not None
            and decision.timezone is not None
        ):
            await self.reminder_service.create_reminder(
                CreateReminderCommand(
                    text=decision.content,
                    remind_at=decision.remind_at,
                    timezone=decision.timezone,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    source_channel=command.channel,
                    source_user_id=command.user_identity,
                    source_chat_id=command.chat_id,
                    source_thread_id=command.thread_id,
                    dispatch_channel=command.channel,
                    dispatch_recipient_id=command.user_identity,
                    dispatch_chat_id=command.chat_id,
                    dispatch_thread_id=command.thread_id,
                )
            )
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by="reminder",
                reason=f"reminder_created_via_{decision.source}",
                response_text=(
                    f"好的，我会在 {decision.remind_at.isoformat()} 提醒你：{decision.content}"
                ),
            )
        if decision.intent == ConversationIntent.REMINDER_CANCEL:
            await self.reminder_service.cancel_latest_reminder(
                conversation_id=conversation_id,
                session_id=session_id,
            )
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by="reminder",
                reason=f"reminder_canceled_via_{decision.source}",
                response_text="好的，已取消最近一条提醒。",
            )
        if decision.intent == ConversationIntent.REMINDER_LIST:
            reminder_list = await self.reminder_service.list_reminders(
                ListRemindersQuery(
                    conversation_id=conversation_id,
                    session_id=session_id,
                    limit=5,
                )
            )
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by="reminder",
                reason=f"reminder_listed_via_{decision.source}",
                response_text=_format_reminder_list_text(reminder_list),
            )
        if decision.intent == ConversationIntent.MEMORY_WRITE and decision.content is not None:
            await self.memory_service.create_memory(
                CreateMemoryCommand(
                    content=decision.content,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    source_channel=command.channel,
                    source_user_id=command.user_identity,
                    source_chat_id=command.chat_id,
                    source_thread_id=command.thread_id,
                )
            )
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by="memory",
                reason=f"memory_created_via_{decision.source}",
                response_text=f"好的，我记住了：{decision.content}",
            )
        if decision.intent == ConversationIntent.MEMORY_ARCHIVE:
            await self.memory_service.archive_latest_memory(
                conversation_id=conversation_id,
                session_id=session_id,
            )
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by="memory",
                reason=f"memory_archived_via_{decision.source}",
                response_text="好的，已归档最近一条记忆。",
            )
        if decision.intent == ConversationIntent.MEMORY_LIST:
            memory_list = await self.memory_service.list_memories(
                ListMemoriesQuery(
                    conversation_id=conversation_id,
                    session_id=session_id,
                    limit=5,
                )
            )
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by="memory",
                reason=f"memory_listed_via_{decision.source}",
                response_text=_format_memory_list_text(memory_list),
            )
        if decision.intent == ConversationIntent.TASK_CANCEL:
            await self.task_service.cancel_latest_task(
                conversation_id=conversation_id,
                session_id=session_id,
            )
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by="task",
                reason=f"task_canceled_via_{decision.source}",
                response_text="好的，已取消最近一条待办。",
            )
        if decision.intent == ConversationIntent.OVERVIEW_SHOW:
            overview = await self.overview_service.get_overview(
                GetOverviewQuery(
                    conversation_id=conversation_id,
                    session_id=session_id,
                )
            )
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by="overview",
                reason=f"overview_shown_via_{decision.source}",
                response_text=_format_overview_text(overview),
            )
        return None


def _classify_with_rules(
    command: HandleInboundConversationMessageCommand,
) -> ConversationIntentDecision:
    reminder_request = _extract_reminder_request(command)
    if reminder_request is not None:
        return reminder_request

    task_title = _extract_task_title(command)
    if task_title is not None:
        return ConversationIntentDecision(
            intent=ConversationIntent.TASK_CREATE,
            content=task_title,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    if _is_task_complete_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.TASK_COMPLETE,
            content=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    if _is_task_list_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.TASK_LIST,
            content=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    if _is_task_cancel_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.TASK_CANCEL,
            content=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    memory_content = _extract_memory_content(command)
    if memory_content is not None:
        return ConversationIntentDecision(
            intent=ConversationIntent.MEMORY_WRITE,
            content=memory_content,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    if _is_memory_archive_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.MEMORY_ARCHIVE,
            content=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    if _is_memory_list_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.MEMORY_LIST,
            content=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    if _is_reminder_cancel_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.REMINDER_CANCEL,
            content=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    if _is_reminder_list_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.REMINDER_LIST,
            content=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    if _is_overview_request(command):
        return ConversationIntentDecision(
            intent=ConversationIntent.OVERVIEW_SHOW,
            content=None,
            remind_at=None,
            timezone=None,
            source="rules",
        )

    return ConversationIntentDecision(
        intent=ConversationIntent.UNKNOWN,
        content=None,
        remind_at=None,
        timezone=None,
        source="rules",
    )


def _build_intent_system_prompt() -> str:
    return (
        "你是 CognitiveOS 的对话意图分类器。"
        "你只负责判断当前文本是否应该创建 reminder、取消 reminder、创建 task、"
        "完成 task、取消 task、写入 memory、归档 memory，或者都不是。"
        "你必须返回 JSON，格式为"
        '{"intent":"reminder_create|reminder_cancel|reminder_list|task_create|task_complete|task_cancel|task_list|memory_write|memory_archive|memory_list|overview_show|unknown",'
        '"content":"提取后的正文或 null",'
        '"remind_at":"ISO8601时间或 null","timezone":"时区或 null"}。'
        "如果文本是在表达未来要提醒的事项，返回 reminder_create，"
        "并提取提醒正文、带时区的 ISO8601 提醒时间，以及 IANA 时区字符串；"
        "如果文本是在要求取消当前会话最近一个提醒，返回 reminder_cancel；"
        "如果文本是在要求查看当前会话里的提醒列表，返回 reminder_list；"
        "如果文本是在表达待办事项，返回 task_create；"
        "如果文本是在要求完成当前会话里最近一个待办，返回 task_complete；"
        "如果文本是在要求取消当前会话里最近一个待办，返回 task_cancel；"
        "如果文本是在要求查看当前会话里的待办列表，返回 task_list；"
        "如果文本是在要求系统记住某件事实或偏好，返回 memory_write；"
        "如果文本是在要求归档当前会话里最近一条活跃记忆，返回 memory_archive；"
        "如果文本是在要求查看当前会话里的记忆列表，返回 memory_list；"
        "如果文本是在要求查看当前会话概览，返回 overview_show；"
        "否则返回 unknown。"
    )


def _build_intent_prompt(text: str) -> str:
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
    elif intent not in {
        ConversationIntent.UNKNOWN,
        ConversationIntent.REMINDER_CANCEL,
        ConversationIntent.REMINDER_LIST,
        ConversationIntent.TASK_COMPLETE,
        ConversationIntent.TASK_CANCEL,
        ConversationIntent.TASK_LIST,
        ConversationIntent.MEMORY_ARCHIVE,
        ConversationIntent.MEMORY_LIST,
        ConversationIntent.OVERVIEW_SHOW,
    }:
        return None
    return ConversationIntentDecision(
        intent=intent,
        content=normalized_content,
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
            return None
        remind_at_text, reminder_content = parts
        try:
            remind_at = datetime.fromisoformat(remind_at_text)
        except ValueError:
            return None
        timezone = str(remind_at.tzinfo) if remind_at.tzinfo is not None else None
        if timezone is None:
            return None
        reminder_content = reminder_content.strip()
        if not reminder_content:
            return None
        return ConversationIntentDecision(
            intent=ConversationIntent.REMINDER_CREATE,
            content=reminder_content,
            remind_at=remind_at,
            timezone=timezone,
            source="rules",
        )

    return None


def _is_task_complete_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {"完成任务", "完成待办", "done task", "complete task"}


def _is_task_list_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {"查看待办", "查看任务", "task list", "show tasks"}


def _is_task_cancel_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {"取消任务", "取消待办", "cancel task"}


def _is_memory_archive_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {"归档记忆", "archive memory", "归档这条记忆"}


def _is_memory_list_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {"查看记忆", "查看记忆列表", "memory list", "show memories"}


def _is_reminder_cancel_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {"取消提醒", "cancel reminder", "取消这个提醒"}


def _is_reminder_list_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {"查看提醒", "查看提醒列表", "reminder list", "show reminders"}


def _is_overview_request(command: HandleInboundConversationMessageCommand) -> bool:
    if command.message_type != "text" or command.text is None:
        return False
    normalized = command.text.strip().casefold()
    return normalized in {"查看概览", "看看概览", "今天有什么", "show overview", "overview"}


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

    return "\n".join(lines)


def _format_task_list_text(task_list: TaskListDTO) -> str:
    if not task_list.items:
        return "当前没有待办任务。"
    lines = ["当前任务："]
    for task in task_list.items:
        lines.append(f"- [{task.status}] {task.title}")
    return "\n".join(lines)


def _format_reminder_list_text(reminder_list: ReminderListDTO) -> str:
    if not reminder_list.items:
        return "当前没有提醒。"
    lines = ["当前提醒："]
    for reminder in reminder_list.items:
        lines.append(f"- [{reminder.status}] {reminder.text} @ {reminder.remind_at.isoformat()}")
    return "\n".join(lines)


def _format_memory_list_text(memory_list: MemoryListDTO) -> str:
    if not memory_list.items:
        return "当前没有记忆。"
    lines = ["当前记忆："]
    for memory in memory_list.items:
        lines.append(f"- [{memory.status}] {memory.content}")
    return "\n".join(lines)
