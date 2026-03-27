import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.state import AssistantTurnContext
from app.application.conversations.kernel.tool_adapter import (
    build_tool_definition,
    to_anthropic_tools,
    to_openai_tools,
)
from app.application.memory.commands import ArchiveMemoryCommand, CreateMemoryCommand
from app.application.memory.queries import ListMemoriesQuery
from app.application.overview.queries import GetOverviewQuery
from app.application.reminders.commands import (
    AcknowledgeReminderCommand,
    CancelAllRemindersCommand,
    CancelReminderCommand,
    CreateReminderCommand,
    RescheduleReminderCommand,
    RetryFailedReminderCommand,
)
from app.application.reminders.queries import ListRemindersQuery
from app.application.tasks.commands import CancelTaskCommand, CompleteTaskCommand, CreateTaskCommand
from app.application.tasks.queries import ListTasksQuery
from app.domain.reminders.value_objects import ReminderRecurrence
from app.infrastructure.tools.mcp.protocol import (
    ToolCall,
    ToolDefinition,
    ToolError,
    ToolExecutionOptions,
    ToolResult,
)
from app.infrastructure.tools.runtime.executor import ToolRuntime
from app.infrastructure.types import JSONObject, JSONValue

logger = logging.getLogger(__name__)


class ReminderToolService(Protocol):
    async def create_reminder(self, command: CreateReminderCommand) -> object: ...
    async def get_reminder(self, reminder_id: str) -> object: ...
    async def list_reminders(self, query: ListRemindersQuery) -> object: ...
    async def list_active_reminders(self, query: ListRemindersQuery) -> object: ...
    async def acknowledge_reminder(self, command: AcknowledgeReminderCommand) -> object: ...
    async def cancel_reminder(self, command: CancelReminderCommand) -> object: ...
    async def cancel_all_reminders(self, command: CancelAllRemindersCommand) -> object: ...
    async def reschedule_reminder(self, command: RescheduleReminderCommand) -> object: ...
    async def retry_failed_reminder(self, command: RetryFailedReminderCommand) -> object: ...


class TaskToolService(Protocol):
    async def create_task(self, command: CreateTaskCommand) -> object: ...
    async def get_task(self, task_id: str) -> object: ...
    async def list_tasks(self, query: ListTasksQuery) -> object: ...
    async def complete_task(self, command: CompleteTaskCommand) -> object: ...
    async def complete_latest_task(self, *, conversation_id: str, session_id: str) -> object: ...
    async def complete_matching_task(
        self,
        *,
        conversation_id: str,
        session_id: str,
        title_hint: str,
    ) -> object: ...
    async def cancel_task(self, command: CancelTaskCommand) -> object: ...
    async def cancel_latest_task(self, *, conversation_id: str, session_id: str) -> object: ...
    async def cancel_matching_task(
        self,
        *,
        conversation_id: str,
        session_id: str,
        title_hint: str,
    ) -> object: ...


class MemoryToolService(Protocol):
    async def create_memory(self, command: CreateMemoryCommand) -> object: ...
    async def get_memory(self, memory_id: str) -> object: ...
    async def list_memories(self, query: ListMemoriesQuery) -> object: ...
    async def archive_memory(self, command: ArchiveMemoryCommand) -> object: ...
    async def archive_latest_memory(self, *, conversation_id: str, session_id: str) -> object: ...
    async def archive_matching_memory(
        self,
        *,
        conversation_id: str,
        session_id: str,
        content_hint: str,
    ) -> object: ...


class OverviewToolService(Protocol):
    async def get_overview(self, query: GetOverviewQuery) -> object: ...
    async def get_today_view(self, query: GetOverviewQuery) -> object: ...
    async def get_working_set_view(self, query: GetOverviewQuery) -> object: ...


class ToolInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConversationScopedToolInput(ToolInputModel):
    conversation_id: str | None = Field(default=None, description="覆盖当前会话 ID。")
    session_id: str | None = Field(default=None, description="覆盖当前 session ID。")


class ReminderRecurrenceInput(ToolInputModel):
    recurrence_type: str = Field(
        ...,
        description="当前仅支持 weekly_by_weekdays。",
    )
    weekdays: list[str] = Field(default_factory=list, description="循环提醒的周几列表。")
    hour: int = Field(default=9, ge=0, le=23, description="循环提醒小时。")
    minute: int = Field(default=0, ge=0, le=59, description="循环提醒分钟。")


class CreateReminderToolInput(ConversationScopedToolInput):
    text: str = Field(..., description="提醒内容。")
    remind_at: datetime = Field(..., description="提醒时间，必须带时区。")
    timezone: str = Field(..., description="提醒时区。")
    recurrence: ReminderRecurrenceInput | None = Field(default=None, description="循环规则。")
    linked_task_id: str | None = Field(default=None, description="关联待办 ID。")


class ReminderIdentifierToolInput(ToolInputModel):
    reminder_id: str = Field(..., description="提醒 ID。")


class ListReminderToolInput(ConversationScopedToolInput):
    status: str | None = Field(default=None, description="提醒状态过滤。")
    query: str | None = Field(default=None, description="提醒内容模糊搜索。")
    limit: int = Field(default=20, ge=1, le=100, description="最大返回数量。")


class ListActiveReminderToolInput(ConversationScopedToolInput):
    query: str | None = Field(default=None, description="提醒内容模糊搜索。")
    limit: int = Field(default=20, ge=1, le=100, description="最大返回数量。")


class AcknowledgeReminderToolInput(ReminderIdentifierToolInput):
    reply_text: str = Field(..., description="用户对提醒的回复内容。")


class CancelAllRemindersToolInput(ConversationScopedToolInput):
    pass


class RescheduleReminderToolInput(ReminderIdentifierToolInput):
    remind_at: datetime = Field(..., description="新的提醒时间，必须带时区。")
    timezone: str = Field(..., description="新的提醒时区。")
    text: str | None = Field(default=None, description="可选的新提醒文本。")


class CreateTaskToolInput(ConversationScopedToolInput):
    title: str = Field(..., description="待办标题。")
    linked_reminder_id: str | None = Field(default=None, description="关联提醒 ID。")
    source_type: str | None = Field(default=None, description="来源类型。")
    source_id: str | None = Field(default=None, description="来源对象 ID。")


class TaskIdentifierToolInput(ToolInputModel):
    task_id: str = Field(..., description="待办 ID。")


class ListTaskToolInput(ConversationScopedToolInput):
    status: str | None = Field(default=None, description="待办状态过滤。")
    query: str | None = Field(default=None, description="待办标题模糊搜索。")
    limit: int = Field(default=20, ge=1, le=100, description="最大返回数量。")


class TaskTitleHintToolInput(ConversationScopedToolInput):
    title_hint: str = Field(..., description="待办标题片段。")


class CreateMemoryToolInput(ConversationScopedToolInput):
    content: str = Field(..., description="记忆内容。")
    memory_type: str | None = Field(default=None, description="记忆类型。")
    scope_object_type: str | None = Field(default=None, description="关联对象类型。")
    scope_object_id: str | None = Field(default=None, description="关联对象 ID。")
    importance: int = Field(default=3, ge=1, le=5, description="记忆重要度。")
    expires_at: datetime | None = Field(default=None, description="过期时间。")


class MemoryIdentifierToolInput(ToolInputModel):
    memory_id: str = Field(..., description="记忆 ID。")


class ListMemoryToolInput(ConversationScopedToolInput):
    status: str | None = Field(default=None, description="记忆状态过滤。")
    query: str | None = Field(default=None, description="记忆内容模糊搜索。")
    limit: int = Field(default=20, ge=1, le=100, description="最大返回数量。")


class MemoryContentHintToolInput(ConversationScopedToolInput):
    content_hint: str = Field(..., description="记忆内容片段。")


class OverviewToolInput(ConversationScopedToolInput):
    reminder_limit: int = Field(default=5, ge=0, le=100, description="提醒数量上限。")
    task_limit: int = Field(default=5, ge=0, le=100, description="待办数量上限。")
    memory_limit: int = Field(default=5, ge=0, le=100, description="记忆数量上限。")
    recent_activity_limit: int = Field(default=5, ge=0, le=100, description="活动数量上限。")


class SpawnBackgroundWorkerInput(ToolInputModel):
    goal: str = Field(..., description="后台任务目标。")


ToolHandler = Callable[[BaseModel, "ToolExecutionContext"], Awaitable[object]]


@dataclass(slots=True, frozen=True)
class ToolExecutionContext:
    command: HandleInboundConversationMessageCommand
    conversation_id: str
    session_id: str
    turn_context: AssistantTurnContext
    trace_id: str | None = None
    chain_id: str | None = None
    request_id: str | None = None


@dataclass(slots=True, frozen=True)
class RegisteredTool:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: ToolHandler
    definition: ToolDefinition


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        input_model: type[BaseModel],
        handler: ToolHandler,
    ) -> RegisteredTool:
        registered = RegisteredTool(
            name=name,
            description=description,
            input_model=input_model,
            handler=handler,
            definition=build_tool_definition(
                name=name,
                description=description,
                input_model=input_model,
            ),
        )
        self._tools[name] = registered
        return registered

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def all(self) -> list[RegisteredTool]:
        return list(self._tools.values())

    def definitions(
        self,
        provider: str | None = None,
    ) -> list[ToolDefinition] | list[JSONObject]:
        definitions = [tool.definition for tool in self._tools.values()]
        if provider is None:
            return definitions
        normalized_provider = provider.strip().casefold()
        if normalized_provider == "openai":
            return to_openai_tools(definitions)
        if normalized_provider == "anthropic":
            return to_anthropic_tools(definitions)
        raise ValueError(f"不支持的工具 schema provider：{provider}")


class RegistryToolRuntime(ToolRuntime):
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        execution_context: ToolExecutionContext,
    ) -> None:
        self.registry = registry
        self.execution_context = execution_context

    async def execute(
        self,
        call: ToolCall,
        options: ToolExecutionOptions | None = None,
    ) -> ToolResult:
        registered = self.registry.get(call.name)
        if registered is None:
            return _build_error_tool_result(
                code="ToolNotFoundError",
                message=f"未注册的工具：{call.name}",
            )

        try:
            parsed_input = registered.input_model.model_validate(call.arguments)
        except ValidationError as exc:
            return _build_error_tool_result(
                code="ToolValidationError",
                message=str(exc),
                details={"validation_errors": cast(JSONValue, exc.errors())},
            )

        effective_options = options or call.options
        max_attempts = max(effective_options.retry_limit, 0) + 1

        for attempt in range(1, max_attempts + 1):
            try:
                result = await self._invoke_handler(
                    registered=registered,
                    parsed_input=parsed_input,
                    timeout_seconds=effective_options.timeout_seconds,
                )
                if isinstance(result, ToolResult):
                    return result
                structured_output = _serialize_to_json_value(result)
                return ToolResult(
                    content=json.dumps(structured_output, ensure_ascii=False),
                    metadata={
                        "structured_output": structured_output,
                        "attempt_count": attempt,
                    },
                )
            except TimeoutError:
                if attempt < max_attempts:
                    continue
                return _build_error_tool_result(
                    code="ToolTimeoutError",
                    message=f"工具执行超时：{call.name}",
                    details={"attempt_count": attempt},
                )
            except Exception as exc:
                if attempt < max_attempts:
                    continue
                return _build_error_tool_result(
                    code=type(exc).__name__,
                    message=str(exc),
                    details={"attempt_count": attempt},
                )

        return _build_error_tool_result(
            code="ToolExecutionError",
            message=f"工具执行失败：{call.name}",
        )

    async def _invoke_handler(
        self,
        *,
        registered: RegisteredTool,
        parsed_input: BaseModel,
        timeout_seconds: float | None,
    ) -> object:
        coroutine = registered.handler(parsed_input, self.execution_context)
        if timeout_seconds is None:
            return await coroutine
        return await asyncio.wait_for(coroutine, timeout=timeout_seconds)


def build_default_tool_registry(
    *,
    reminder_service: ReminderToolService,
    task_service: TaskToolService,
    memory_service: MemoryToolService,
    overview_service: OverviewToolService,
) -> ToolRegistry:
    registry = ToolRegistry()

    async def create_reminder(
        payload: BaseModel,
        context: ToolExecutionContext,
    ) -> object:
        parsed = cast(CreateReminderToolInput, payload)
        return await reminder_service.create_reminder(
            CreateReminderCommand(
                text=parsed.text,
                remind_at=parsed.remind_at,
                timezone=parsed.timezone,
                recurrence=_to_recurrence(parsed.recurrence),
                linked_task_id=parsed.linked_task_id,
                conversation_id=_resolve_conversation_id(parsed, context),
                session_id=_resolve_session_id(parsed, context),
                source_channel=context.command.channel,
                source_user_id=context.command.user_identity,
                source_chat_id=context.command.chat_id,
                source_thread_id=context.command.thread_id,
                dispatch_channel=context.command.channel,
                dispatch_recipient_id=context.command.user_identity,
                dispatch_chat_id=context.command.chat_id,
                dispatch_thread_id=context.command.thread_id,
            )
        )

    async def get_reminder(payload: BaseModel, context: ToolExecutionContext) -> object:
        _ = context
        parsed = cast(ReminderIdentifierToolInput, payload)
        return await reminder_service.get_reminder(parsed.reminder_id)

    async def list_reminders(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(ListReminderToolInput, payload)
        return await reminder_service.list_reminders(
            ListRemindersQuery(
                conversation_id=_resolve_conversation_id(parsed, context),
                session_id=_resolve_session_id(parsed, context),
                status=parsed.status,
                query=parsed.query,
                limit=parsed.limit,
            )
        )

    async def list_active_reminders(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(ListActiveReminderToolInput, payload)
        return await reminder_service.list_active_reminders(
            ListRemindersQuery(
                conversation_id=_resolve_conversation_id(parsed, context),
                session_id=_resolve_session_id(parsed, context),
                query=parsed.query,
                limit=parsed.limit,
            )
        )

    async def acknowledge_reminder(payload: BaseModel, context: ToolExecutionContext) -> object:
        _ = context
        parsed = cast(AcknowledgeReminderToolInput, payload)
        return await reminder_service.acknowledge_reminder(
            AcknowledgeReminderCommand(
                reminder_id=parsed.reminder_id,
                reply_text=parsed.reply_text,
            )
        )

    async def cancel_reminder(payload: BaseModel, context: ToolExecutionContext) -> object:
        _ = context
        parsed = cast(ReminderIdentifierToolInput, payload)
        return await reminder_service.cancel_reminder(
            CancelReminderCommand(reminder_id=parsed.reminder_id)
        )

    async def cancel_all_reminders(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(CancelAllRemindersToolInput, payload)
        return await reminder_service.cancel_all_reminders(
            CancelAllRemindersCommand(
                conversation_id=_resolve_conversation_id(parsed, context),
                session_id=_resolve_session_id(parsed, context),
            )
        )

    async def reschedule_reminder(payload: BaseModel, context: ToolExecutionContext) -> object:
        _ = context
        parsed = cast(RescheduleReminderToolInput, payload)
        return await reminder_service.reschedule_reminder(
            RescheduleReminderCommand(
                reminder_id=parsed.reminder_id,
                remind_at=parsed.remind_at,
                timezone=parsed.timezone,
                text=parsed.text,
            )
        )

    async def retry_failed_reminder(payload: BaseModel, context: ToolExecutionContext) -> object:
        _ = context
        parsed = cast(ReminderIdentifierToolInput, payload)
        return await reminder_service.retry_failed_reminder(
            RetryFailedReminderCommand(reminder_id=parsed.reminder_id)
        )

    async def create_task(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(CreateTaskToolInput, payload)
        return await task_service.create_task(
            CreateTaskCommand(
                title=parsed.title,
                linked_reminder_id=parsed.linked_reminder_id,
                source_type=parsed.source_type,
                source_id=parsed.source_id,
                conversation_id=_resolve_conversation_id(parsed, context),
                session_id=_resolve_session_id(parsed, context),
                source_channel=context.command.channel,
                source_user_id=context.command.user_identity,
                source_chat_id=context.command.chat_id,
                source_thread_id=context.command.thread_id,
            )
        )

    async def get_task(payload: BaseModel, context: ToolExecutionContext) -> object:
        _ = context
        parsed = cast(TaskIdentifierToolInput, payload)
        return await task_service.get_task(parsed.task_id)

    async def list_tasks(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(ListTaskToolInput, payload)
        return await task_service.list_tasks(
            ListTasksQuery(
                conversation_id=_resolve_conversation_id(parsed, context),
                session_id=_resolve_session_id(parsed, context),
                status=parsed.status,
                query=parsed.query,
                limit=parsed.limit,
            )
        )

    async def complete_task(payload: BaseModel, context: ToolExecutionContext) -> object:
        _ = context
        parsed = cast(TaskIdentifierToolInput, payload)
        return await task_service.complete_task(CompleteTaskCommand(task_id=parsed.task_id))

    async def complete_latest_task(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(ConversationScopedToolInput, payload)
        return await task_service.complete_latest_task(
            conversation_id=_resolve_conversation_id(parsed, context),
            session_id=_resolve_session_id(parsed, context),
        )

    async def complete_matching_task(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(TaskTitleHintToolInput, payload)
        return await task_service.complete_matching_task(
            conversation_id=_resolve_conversation_id(parsed, context),
            session_id=_resolve_session_id(parsed, context),
            title_hint=parsed.title_hint,
        )

    async def cancel_task(payload: BaseModel, context: ToolExecutionContext) -> object:
        _ = context
        parsed = cast(TaskIdentifierToolInput, payload)
        return await task_service.cancel_task(CancelTaskCommand(task_id=parsed.task_id))

    async def cancel_latest_task(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(ConversationScopedToolInput, payload)
        return await task_service.cancel_latest_task(
            conversation_id=_resolve_conversation_id(parsed, context),
            session_id=_resolve_session_id(parsed, context),
        )

    async def cancel_matching_task(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(TaskTitleHintToolInput, payload)
        return await task_service.cancel_matching_task(
            conversation_id=_resolve_conversation_id(parsed, context),
            session_id=_resolve_session_id(parsed, context),
            title_hint=parsed.title_hint,
        )

    async def create_memory(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(CreateMemoryToolInput, payload)
        return await memory_service.create_memory(
            CreateMemoryCommand(
                content=parsed.content,
                memory_type=parsed.memory_type,
                conversation_id=_resolve_conversation_id(parsed, context),
                session_id=_resolve_session_id(parsed, context),
                source_channel=context.command.channel,
                source_user_id=context.command.user_identity,
                source_chat_id=context.command.chat_id,
                source_thread_id=context.command.thread_id,
                scope_object_type=parsed.scope_object_type,
                scope_object_id=parsed.scope_object_id,
                importance=parsed.importance,
                expires_at=parsed.expires_at,
            )
        )

    async def get_memory(payload: BaseModel, context: ToolExecutionContext) -> object:
        _ = context
        parsed = cast(MemoryIdentifierToolInput, payload)
        return await memory_service.get_memory(parsed.memory_id)

    async def list_memories(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(ListMemoryToolInput, payload)
        return await memory_service.list_memories(
            ListMemoriesQuery(
                conversation_id=_resolve_conversation_id(parsed, context),
                session_id=_resolve_session_id(parsed, context),
                status=parsed.status,
                query=parsed.query,
                limit=parsed.limit,
            )
        )

    async def archive_memory(payload: BaseModel, context: ToolExecutionContext) -> object:
        _ = context
        parsed = cast(MemoryIdentifierToolInput, payload)
        return await memory_service.archive_memory(ArchiveMemoryCommand(memory_id=parsed.memory_id))

    async def archive_latest_memory(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(ConversationScopedToolInput, payload)
        return await memory_service.archive_latest_memory(
            conversation_id=_resolve_conversation_id(parsed, context),
            session_id=_resolve_session_id(parsed, context),
        )

    async def archive_matching_memory(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(MemoryContentHintToolInput, payload)
        return await memory_service.archive_matching_memory(
            conversation_id=_resolve_conversation_id(parsed, context),
            session_id=_resolve_session_id(parsed, context),
            content_hint=parsed.content_hint,
        )

    async def get_overview(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(OverviewToolInput, payload)
        return await overview_service.get_overview(_build_overview_query(parsed, context))

    async def get_today_view(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(OverviewToolInput, payload)
        return await overview_service.get_today_view(_build_overview_query(parsed, context))

    async def get_working_set_view(payload: BaseModel, context: ToolExecutionContext) -> object:
        parsed = cast(OverviewToolInput, payload)
        return await overview_service.get_working_set_view(_build_overview_query(parsed, context))

    async def spawn_background_worker(
        payload: BaseModel,
        context: ToolExecutionContext,
    ) -> object:
        parsed = cast(SpawnBackgroundWorkerInput, payload)
        logger.info(
            "收到后台委托工具调用，当前返回骨架结果。",
            extra={
                "conversation_id": context.conversation_id,
                "session_id": context.session_id,
                "goal": parsed.goal,
                "trace_id": context.trace_id,
                "chain_id": context.chain_id,
                "request_id": context.request_id,
            },
        )
        return {
            "status": "background_workflow_started",
            "goal": parsed.goal,
        }

    registry.register(
        name="reminders.create",
        description="创建一个新的提醒。",
        input_model=CreateReminderToolInput,
        handler=create_reminder,
    )
    registry.register(
        name="reminders.get",
        description="按提醒 ID 查询提醒详情。",
        input_model=ReminderIdentifierToolInput,
        handler=get_reminder,
    )
    registry.register(
        name="reminders.list",
        description="查询当前会话或指定范围内的提醒列表。",
        input_model=ListReminderToolInput,
        handler=list_reminders,
    )
    registry.register(
        name="reminders.list_active",
        description="查询当前会话或指定范围内仍然生效的提醒。",
        input_model=ListActiveReminderToolInput,
        handler=list_active_reminders,
    )
    registry.register(
        name="reminders.acknowledge",
        description="确认一条提醒已经处理。",
        input_model=AcknowledgeReminderToolInput,
        handler=acknowledge_reminder,
    )
    registry.register(
        name="reminders.cancel",
        description="取消一条提醒。",
        input_model=ReminderIdentifierToolInput,
        handler=cancel_reminder,
    )
    registry.register(
        name="reminders.cancel_all",
        description="取消当前会话或指定范围内的全部提醒。",
        input_model=CancelAllRemindersToolInput,
        handler=cancel_all_reminders,
    )
    registry.register(
        name="reminders.reschedule",
        description="修改一条提醒的时间。",
        input_model=RescheduleReminderToolInput,
        handler=reschedule_reminder,
    )
    registry.register(
        name="reminders.retry_failed",
        description="重试一条失败的提醒。",
        input_model=ReminderIdentifierToolInput,
        handler=retry_failed_reminder,
    )
    registry.register(
        name="tasks.create",
        description="创建一个新的待办。",
        input_model=CreateTaskToolInput,
        handler=create_task,
    )
    registry.register(
        name="tasks.get",
        description="按待办 ID 查询待办详情。",
        input_model=TaskIdentifierToolInput,
        handler=get_task,
    )
    registry.register(
        name="tasks.list",
        description="查询当前会话或指定范围内的待办列表。",
        input_model=ListTaskToolInput,
        handler=list_tasks,
    )
    registry.register(
        name="tasks.complete",
        description="完成一条待办。",
        input_model=TaskIdentifierToolInput,
        handler=complete_task,
    )
    registry.register(
        name="tasks.complete_latest",
        description="完成当前会话最近的一条待办。",
        input_model=ConversationScopedToolInput,
        handler=complete_latest_task,
    )
    registry.register(
        name="tasks.complete_matching",
        description="按标题片段完成一条待办。",
        input_model=TaskTitleHintToolInput,
        handler=complete_matching_task,
    )
    registry.register(
        name="tasks.cancel",
        description="取消一条待办。",
        input_model=TaskIdentifierToolInput,
        handler=cancel_task,
    )
    registry.register(
        name="tasks.cancel_latest",
        description="取消当前会话最近的一条待办。",
        input_model=ConversationScopedToolInput,
        handler=cancel_latest_task,
    )
    registry.register(
        name="tasks.cancel_matching",
        description="按标题片段取消一条待办。",
        input_model=TaskTitleHintToolInput,
        handler=cancel_matching_task,
    )
    registry.register(
        name="memories.create",
        description="写入一条新记忆。",
        input_model=CreateMemoryToolInput,
        handler=create_memory,
    )
    registry.register(
        name="memories.get",
        description="按记忆 ID 查询记忆详情。",
        input_model=MemoryIdentifierToolInput,
        handler=get_memory,
    )
    registry.register(
        name="memories.list",
        description="查询当前会话或指定范围内的记忆列表。",
        input_model=ListMemoryToolInput,
        handler=list_memories,
    )
    registry.register(
        name="memories.archive",
        description="归档一条记忆。",
        input_model=MemoryIdentifierToolInput,
        handler=archive_memory,
    )
    registry.register(
        name="memories.archive_latest",
        description="归档当前会话最近的一条记忆。",
        input_model=ConversationScopedToolInput,
        handler=archive_latest_memory,
    )
    registry.register(
        name="memories.archive_matching",
        description="按内容片段归档一条记忆。",
        input_model=MemoryContentHintToolInput,
        handler=archive_matching_memory,
    )
    registry.register(
        name="overview.get",
        description="查看当前会话概览。",
        input_model=OverviewToolInput,
        handler=get_overview,
    )
    registry.register(
        name="overview.today",
        description="查看今天相关的概览。",
        input_model=OverviewToolInput,
        handler=get_today_view,
    )
    registry.register(
        name="overview.working_set",
        description="查看当前 working set 概览。",
        input_model=OverviewToolInput,
        handler=get_working_set_view,
    )
    registry.register(
        name="system.spawn_background_worker",
        description=(
            "当用户的请求极其复杂、需要长耗时处理（例如批量数据分析、长文本总结、复杂规划）时调用。"
            "调用此工具后系统会在后台启动独立进程处理，并立即向用户回复后台已接管。"
        ),
        input_model=SpawnBackgroundWorkerInput,
        handler=spawn_background_worker,
    )
    return registry


def _build_error_tool_result(
    *,
    code: str,
    message: str,
    details: JSONObject | None = None,
) -> ToolResult:
    payload: JSONObject = {
        "error": {
            "code": code,
            "message": message,
        }
    }
    if details:
        payload["error"]["details"] = details
    return ToolResult(
        content=json.dumps(payload, ensure_ascii=False),
        is_error=True,
        error=ToolError(code=code, message=message),
        metadata={"structured_output": payload},
    )


def _build_overview_query(
    payload: OverviewToolInput,
    context: ToolExecutionContext,
) -> GetOverviewQuery:
    return GetOverviewQuery(
        conversation_id=_resolve_conversation_id(payload, context),
        session_id=_resolve_session_id(payload, context),
        reminder_limit=payload.reminder_limit,
        task_limit=payload.task_limit,
        memory_limit=payload.memory_limit,
        recent_activity_limit=payload.recent_activity_limit,
    )


def _resolve_conversation_id(
    payload: ConversationScopedToolInput,
    context: ToolExecutionContext,
) -> str:
    return payload.conversation_id or context.conversation_id


def _resolve_session_id(
    payload: ConversationScopedToolInput,
    context: ToolExecutionContext,
) -> str:
    return payload.session_id or context.session_id


def _to_recurrence(payload: ReminderRecurrenceInput | None) -> ReminderRecurrence | None:
    if payload is None:
        return None
    return ReminderRecurrence(
        recurrence_type=payload.recurrence_type,
        weekdays=tuple(payload.weekdays),
        hour=payload.hour,
        minute=payload.minute,
    )


def _serialize_to_json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, str | int | float | bool):
        return cast(JSONValue, value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return _serialize_to_json_value(value.value)
    if isinstance(value, BaseModel):
        return _serialize_to_json_value(value.model_dump(mode="json"))
    if is_dataclass(value):
        return _serialize_to_json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _serialize_to_json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_serialize_to_json_value(item) for item in value]
    return str(value)
