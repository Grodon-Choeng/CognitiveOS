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
from app.application.memory.errors import MemoryApplicationError
from app.application.memory.queries import ListMemoriesQuery
from app.application.overview.dto import OverviewDTO
from app.application.overview.queries import GetOverviewQuery
from app.application.reminders.commands import CreateReminderCommand
from app.application.reminders.dto import ReminderDTO, ReminderListDTO
from app.application.reminders.errors import ReminderApplicationError
from app.application.reminders.queries import ListRemindersQuery
from app.application.tasks.commands import CreateTaskCommand
from app.application.tasks.conversation_handler import _extract_task_title
from app.application.tasks.dto import TaskDTO, TaskListDTO
from app.application.tasks.errors import TaskApplicationError
from app.application.tasks.queries import ListTasksQuery
from app.infrastructure.llm.gateway import LLMGateway
from app.infrastructure.llm.models import GenerateRequest


class ConversationIntent(StrEnum):
    GREETING = "greeting"
    HELP_SHOW = "help_show"
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
    ) -> ConversationIntentDecision:
        llm_decision = await self._classify_with_llm(
            command=command,
            conversation_id=conversation_id,
            session_id=session_id,
            context_text=context_text,
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
        context_text: str | None,
    ) -> ConversationIntentDecision | None:
        if self.llm_gateway is None or self.model is None:
            return None
        if command.message_type != "text" or command.text is None:
            return None

        try:
            result = await self.llm_gateway.generate(
                GenerateRequest(
                    prompt=_build_intent_prompt(command.text, context_text),
                    system_prompt=_build_intent_system_prompt(),
                    provider=self.provider,
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
        context_text = await self._build_context_text(
            conversation_id=conversation_id,
            session_id=session_id,
        )
        decision = await self.classifier.classify(
            command,
            conversation_id=conversation_id,
            session_id=session_id,
            context_text=context_text,
        )
        try:
            if decision.intent == ConversationIntent.GREETING:
                return ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by="conversation",
                    reason=f"greeting_replied_via_{decision.source}",
                    response_text=(
                        "你好，我可以帮你记提醒、建待办、记住信息，"
                        "也可以帮你查看概览、提醒、待办和记忆。"
                    ),
                )
            if decision.intent == ConversationIntent.HELP_SHOW:
                return ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by="conversation",
                    reason=f"help_shown_via_{decision.source}",
                    response_text=(
                        "我现在主要能帮你做这些事：\n"
                        "- 提醒：例如“提醒：2026-03-24T09:00:00+08:00 开会”\n"
                        "- 待办：例如“待办：整理周报”\n"
                        "- 记忆：例如“记住：我喜欢早上九点提醒”\n"
                        "- 查询：例如“查看概览”“查看待办”“查看提醒”“查看记忆”\n"
                        "- 动作：例如“完成任务 周报”“取消提醒 开会”“归档记忆 九点提醒”"
                    ),
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
                        status=decision.status,
                        query=decision.content,
                        limit=5,
                    )
                )
                return ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by="task",
                    reason=f"task_listed_via_{decision.source}",
                    response_text=_format_task_list_text(
                        task_list,
                        decision.status,
                        decision.content,
                    ),
                )
            if decision.intent == ConversationIntent.TASK_COMPLETE:
                if decision.content:
                    completed_task = await self.task_service.complete_matching_task(
                        conversation_id=conversation_id,
                        session_id=session_id,
                        title_hint=decision.content,
                    )
                else:
                    completed_task = await self.task_service.complete_latest_task(
                        conversation_id=conversation_id,
                        session_id=session_id,
                    )
                return ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by="task",
                    reason=f"task_completed_via_{decision.source}",
                    response_text=f"好的，已完成待办：{completed_task.title}",
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
                if decision.content:
                    canceled_reminder = await self.reminder_service.cancel_matching_reminder(
                        conversation_id=conversation_id,
                        session_id=session_id,
                        text_hint=decision.content,
                    )
                else:
                    canceled_reminder = await self.reminder_service.cancel_latest_reminder(
                        conversation_id=conversation_id,
                        session_id=session_id,
                    )
                return ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by="reminder",
                    reason=f"reminder_canceled_via_{decision.source}",
                    response_text=f"好的，已取消提醒：{canceled_reminder.text}",
                )
            if decision.intent == ConversationIntent.REMINDER_LIST:
                reminder_list = await self.reminder_service.list_reminders(
                    ListRemindersQuery(
                        conversation_id=conversation_id,
                        session_id=session_id,
                        status=decision.status,
                        query=decision.content,
                        limit=5,
                    )
                )
                return ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by="reminder",
                    reason=f"reminder_listed_via_{decision.source}",
                    response_text=_format_reminder_list_text(
                        reminder_list,
                        decision.status,
                        decision.content,
                    ),
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
                if decision.content:
                    archived_memory = await self.memory_service.archive_matching_memory(
                        conversation_id=conversation_id,
                        session_id=session_id,
                        content_hint=decision.content,
                    )
                else:
                    archived_memory = await self.memory_service.archive_latest_memory(
                        conversation_id=conversation_id,
                        session_id=session_id,
                    )
                return ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by="memory",
                    reason=f"memory_archived_via_{decision.source}",
                    response_text=f"好的，已归档记忆：{archived_memory.content}",
                )
            if decision.intent == ConversationIntent.MEMORY_LIST:
                memory_list = await self.memory_service.list_memories(
                    ListMemoriesQuery(
                        conversation_id=conversation_id,
                        session_id=session_id,
                        status=decision.status,
                        query=decision.content,
                        limit=5,
                    )
                )
                return ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by="memory",
                    reason=f"memory_listed_via_{decision.source}",
                    response_text=_format_memory_list_text(memory_list, decision.status),
                )
            if decision.intent == ConversationIntent.TASK_CANCEL:
                if decision.content:
                    canceled_task = await self.task_service.cancel_matching_task(
                        conversation_id=conversation_id,
                        session_id=session_id,
                        title_hint=decision.content,
                    )
                else:
                    canceled_task = await self.task_service.cancel_latest_task(
                        conversation_id=conversation_id,
                        session_id=session_id,
                    )
                return ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by="task",
                    reason=f"task_canceled_via_{decision.source}",
                    response_text=f"好的，已取消待办：{canceled_task.title}",
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
            if decision.intent == ConversationIntent.ACTIVITY_SHOW:
                overview = await self.overview_service.get_overview(
                    GetOverviewQuery(
                        conversation_id=conversation_id,
                        session_id=session_id,
                        reminder_limit=0,
                        task_limit=0,
                        memory_limit=0,
                        recent_activity_limit=5,
                    )
                )
                return ConversationInboundResult(
                    handled=True,
                    conversation_id=conversation_id,
                    session_id=session_id,
                    handled_by="overview",
                    reason=f"activity_shown_via_{decision.source}",
                    response_text=_format_recent_activity_text(overview),
                )
            return None
        except (TaskApplicationError, MemoryApplicationError, ReminderApplicationError) as exc:
            handled_by = _handled_by_for_intent(decision.intent)
            if handled_by is None:
                raise
            return ConversationInboundResult(
                handled=True,
                conversation_id=conversation_id,
                session_id=session_id,
                handled_by=handled_by,
                reason=f"{decision.intent.value}_feedback",
                response_text=str(exc),
            )

    async def _build_context_text(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> str | None:
        if self.classifier.llm_gateway is None or self.classifier.model is None:
            return None
        try:
            overview = await self.overview_service.get_overview(
                GetOverviewQuery(
                    conversation_id=conversation_id,
                    session_id=session_id,
                    reminder_limit=3,
                    task_limit=3,
                    memory_limit=3,
                    recent_activity_limit=3,
                )
            )
        except Exception:
            return None
        return _format_overview_context_hint(overview)


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
        "完成 task、取消 task、写入 memory、归档 memory，或者都不是。"
        "你必须返回 JSON，格式为"
        '{"intent":"greeting|help_show|reminder_create|reminder_cancel|reminder_list|task_create|task_complete|task_cancel|task_list|memory_write|memory_archive|memory_list|overview_show|activity_show|unknown",'
        '"content":"提取后的正文或 null",'
        '"status":"pending|completed|canceled|failed|active|archived|unknown|null",'
        '"remind_at":"ISO8601时间或 null","timezone":"时区或 null"}。'
        "如果文本只是打招呼，例如 hi、hello、hey、你好，返回 greeting；"
        "如果文本是在询问你能做什么、如何使用、help，返回 help_show；"
        "如果文本是在表达未来要提醒的事项，返回 reminder_create，"
        "并提取提醒正文、带时区的 ISO8601 提醒时间，以及 IANA 时区字符串；"
        "如果文本是在要求取消当前会话最近一个提醒，返回 reminder_cancel；"
        "如果文本是在要求查看当前会话里的提醒列表，返回 reminder_list；"
        "如果文本是在要求按关键词查找提醒，也返回 reminder_list，并把关键词写到 content；"
        "如果文本是在表达待办事项，返回 task_create；"
        "如果文本是在要求完成当前会话里最近一个待办，返回 task_complete；"
        "如果文本是在要求取消当前会话里最近一个待办，返回 task_cancel；"
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
    elif intent not in {
        ConversationIntent.GREETING,
        ConversationIntent.HELP_SHOW,
        ConversationIntent.UNKNOWN,
        ConversationIntent.REMINDER_CANCEL,
        ConversationIntent.REMINDER_LIST,
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
            status=None,
            remind_at=remind_at,
            timezone=timezone,
            source="rules",
        )

    return None


def _is_task_complete_request(command: HandleInboundConversationMessageCommand) -> bool:
    matched, _ = _extract_action_content(
        command,
        prefixes=("完成任务", "完成待办", "done task", "complete task"),
    )
    return matched


def _is_task_list_request(command: HandleInboundConversationMessageCommand) -> bool:
    return _extract_task_list_status(command) is not None


def _is_task_cancel_request(command: HandleInboundConversationMessageCommand) -> bool:
    matched, _ = _extract_action_content(
        command,
        prefixes=("取消任务", "取消待办", "cancel task"),
    )
    return matched


def _is_memory_archive_request(command: HandleInboundConversationMessageCommand) -> bool:
    matched, _ = _extract_action_content(
        command,
        prefixes=("归档记忆", "archive memory", "归档这条记忆"),
    )
    return matched


def _is_memory_list_request(command: HandleInboundConversationMessageCommand) -> bool:
    return _extract_memory_list_status(command) is not None


def _is_reminder_cancel_request(command: HandleInboundConversationMessageCommand) -> bool:
    matched, _ = _extract_action_content(
        command,
        prefixes=("取消提醒", "cancel reminder", "取消这个提醒"),
    )
    return matched


def _is_reminder_list_request(command: HandleInboundConversationMessageCommand) -> bool:
    return _extract_reminder_list_status(command) is not None


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
