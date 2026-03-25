from typing import Protocol

from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.resolver import ReferenceResolver
from app.application.conversations.kernel.results import (
    AssistantConfirmationResult,
    AssistantDisambiguationResult,
    AssistantExecutionResult,
)
from app.application.conversations.kernel.state import AssistantTurnContext
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

KernelExecutionResult = (
    AssistantExecutionResult | AssistantDisambiguationResult | AssistantConfirmationResult | None
)


class TaskExecutorService(Protocol):
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
    async def cancel_matching_task(
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
    async def list_tasks(self, query: ListTasksQuery) -> TaskListDTO: ...


class ReminderExecutorService(Protocol):
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


class MemoryExecutorService(Protocol):
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


class OverviewExecutorService(Protocol):
    async def get_overview(self, query: GetOverviewQuery) -> OverviewDTO: ...
    async def get_today_view(self, query: GetOverviewQuery) -> OverviewDTO: ...
    async def get_working_set_view(self, query: GetOverviewQuery) -> OverviewDTO: ...


class AssistantExecutor:
    def __init__(
        self,
        *,
        task_service: TaskExecutorService,
        reminder_service: ReminderExecutorService,
        memory_service: MemoryExecutorService,
        overview_service: OverviewExecutorService,
        resolver: ReferenceResolver,
    ) -> None:
        self.task_service = task_service
        self.reminder_service = reminder_service
        self.memory_service = memory_service
        self.overview_service = overview_service
        self.resolver = resolver

    async def execute(
        self,
        plan: AssistantActionPlan,
        *,
        command: HandleInboundConversationMessageCommand,
        turn_context: AssistantTurnContext,
    ) -> KernelExecutionResult:
        try:
            return await self._execute_inner(
                plan,
                command=command,
                turn_context=turn_context,
            )
        except (TaskApplicationError, ReminderApplicationError, MemoryApplicationError) as exc:
            return AssistantExecutionResult(
                success=False,
                action=plan.action or plan.intent,
                object_type=plan.object_type,
                object_id=plan.object_id,
                message_hint=str(exc),
                recovery_options=["换个说法再试一次", "查看概览"],
            )

    async def _execute_inner(
        self,
        plan: AssistantActionPlan,
        *,
        command: HandleInboundConversationMessageCommand,
        turn_context: AssistantTurnContext,
    ) -> KernelExecutionResult:
        if plan.status == "unsupported" or plan.action is None:
            return None

        if plan.action in {
            "complete_task",
            "cancel_task",
            "cancel_reminder",
            "archive_memory",
            "retry_failed_reminder",
            "convert_task_to_reminder",
            "convert_reminder_to_task",
            "reschedule_reminder",
        }:
            plan = self.resolver.resolve(plan, turn_context=turn_context)
            if plan.status == "needs_disambiguation":
                return AssistantDisambiguationResult(
                    prompt="我找到几个可能的对象，你想操作哪一个？",
                    candidates=[
                        {
                            "object_type": candidate.object_type,
                            "object_id": candidate.object_id,
                            "title": candidate.title,
                        }
                        for candidate in plan.candidates
                    ],
                )
            if plan.status == "needs_confirmation":
                candidate = plan.candidates[0] if plan.candidates else None
                preview = candidate.title if candidate is not None else None
                return AssistantConfirmationResult(
                    prompt="我理解成你要操作这条记录，先帮你确认一下。",
                    confirm_action=plan.action or "confirm",
                    preview_text=preview,
                )
            if plan.status != "ready" or plan.object_id is None:
                return None

        if plan.action == "reply_greeting":
            return AssistantExecutionResult(success=True, action=plan.action)
        if plan.action == "show_help":
            return AssistantExecutionResult(success=True, action=plan.action)
        if plan.action == "show_activity":
            overview = await self.overview_service.get_overview(
                GetOverviewQuery(
                    conversation_id=turn_context.conversation_id,
                    session_id=turn_context.session_id,
                    reminder_limit=0,
                    task_limit=0,
                    memory_limit=0,
                    recent_activity_limit=5,
                )
            )
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                payload={
                    "recent_activity": [
                        {"kind": event.kind, "summary": event.summary}
                        for event in overview.recent_activity
                    ]
                },
            )
        if plan.action == "show_overview":
            query = GetOverviewQuery(
                conversation_id=turn_context.conversation_id,
                session_id=turn_context.session_id,
            )
            overview_view = _optional_str(plan.args.get("view"))
            if overview_view == "today":
                overview = await self.overview_service.get_today_view(query)
            elif overview_view == "working_set":
                overview = await self.overview_service.get_working_set_view(query)
            else:
                overview = await self.overview_service.get_overview(query)
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                payload={
                    "view": overview_view or "default",
                    "pending_tasks": [_task_item(task) for task in overview.pending_tasks],
                    "pending_reminders": [
                        _reminder_item(reminder) for reminder in overview.pending_reminders
                    ],
                    "active_memories": [
                        _memory_item(memory) for memory in overview.active_memories
                    ],
                    "focused_object": _focused_object_payload(turn_context),
                    "last_assistant_action": _last_action_payload(turn_context),
                    "recent_activity": [
                        {"kind": event.kind, "summary": event.summary}
                        for event in overview.recent_activity
                    ],
                },
                followup_options=["查看待办", "查看提醒", "查看记忆"],
            )
        if plan.action == "create_task":
            task = await self.task_service.create_task(
                CreateTaskCommand(
                    title=str(plan.args["title"]),
                    conversation_id=turn_context.conversation_id,
                    session_id=turn_context.session_id,
                    source_channel=command.channel,
                    source_user_id=command.user_identity,
                    source_chat_id=command.chat_id,
                    source_thread_id=command.thread_id,
                )
            )
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="task",
                object_id=task.task_id,
                object_title=task.title,
                payload=_task_item(task),
                followup_options=["查看待办", "完成这个", "取消这个"],
            )
        if plan.action == "list_tasks":
            task_list = await self.task_service.list_tasks(
                ListTasksQuery(
                    conversation_id=turn_context.conversation_id,
                    session_id=turn_context.session_id,
                    status=_optional_str(plan.args.get("status")),
                    query=_optional_str(plan.args.get("query")),
                    limit=5,
                )
            )
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="task",
                payload={
                    "status": _optional_str(plan.args.get("status")),
                    "query": _optional_str(plan.args.get("query")),
                    "items": [_task_item(task) for task in task_list.items],
                },
                followup_options=["完成第二个", "取消第一个"],
            )
        if plan.action == "complete_task":
            task = await self._complete_task(plan, turn_context=turn_context)
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="task",
                object_id=task.task_id,
                object_title=task.title,
                payload=_task_item(task),
                followup_options=["查看待办", "查看概览"],
            )
        if plan.action == "cancel_task":
            task = await self._cancel_task(plan, turn_context=turn_context)
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="task",
                object_id=task.task_id,
                object_title=task.title,
                payload=_task_item(task),
                followup_options=["查看待办", "查看概览"],
            )
        if plan.action == "create_reminder":
            reminder = await self.reminder_service.create_reminder(
                CreateReminderCommand(
                    text=str(plan.args["text"]),
                    remind_at=plan.args["remind_at"],
                    timezone=str(plan.args["timezone"]),
                    linked_task_id=_optional_str(plan.args.get("linked_task_id")),
                    conversation_id=turn_context.conversation_id,
                    session_id=turn_context.session_id,
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
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="reminder",
                object_id=reminder.reminder_id,
                object_title=reminder.text,
                payload=_reminder_item(reminder),
                followup_options=["查看提醒", "取消这个提醒"],
            )
        if plan.action == "reschedule_reminder":
            assert plan.object_id is not None
            existing_reminder: ReminderDTO | None = None
            remind_at = plan.args.get("remind_at")
            timezone = _optional_str(plan.args.get("timezone"))
            updated_text = _optional_str(plan.args.get("text"))
            change_kind = "schedule"
            if remind_at is None or timezone is None:
                existing_reminder = await self._get_reminder_from_plan(
                    plan,
                    turn_context=turn_context,
                )
                remind_at = existing_reminder.remind_at
                timezone = existing_reminder.timezone
                change_kind = "content"
            if updated_text is not None and change_kind == "schedule":
                change_kind = "schedule_and_content"
            reminder = await self.reminder_service.reschedule_reminder(
                RescheduleReminderCommand(
                    reminder_id=plan.object_id,
                    remind_at=remind_at,
                    timezone=timezone,
                    text=updated_text,
                )
            )
            payload = _reminder_item(reminder)
            payload["change_kind"] = change_kind
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="reminder",
                object_id=reminder.reminder_id,
                object_title=reminder.text,
                payload=payload,
                followup_options=["查看提醒", "查看概览"],
            )
        if plan.action == "list_reminders":
            reminder_list = await self.reminder_service.list_reminders(
                ListRemindersQuery(
                    conversation_id=turn_context.conversation_id,
                    session_id=turn_context.session_id,
                    status=_optional_str(plan.args.get("status")),
                    query=_optional_str(plan.args.get("query")),
                    limit=5,
                )
            )
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="reminder",
                payload={
                    "status": _optional_str(plan.args.get("status")),
                    "query": _optional_str(plan.args.get("query")),
                    "items": [_reminder_item(reminder) for reminder in reminder_list.items],
                },
                followup_options=(
                    ["重试第一个失败提醒", "查看概览"]
                    if _optional_str(plan.args.get("status")) == "failed"
                    else ["取消第二个", "查看概览"]
                ),
            )
        if plan.action == "cancel_reminder":
            reminder = await self._cancel_reminder(plan, turn_context=turn_context)
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="reminder",
                object_id=reminder.reminder_id,
                object_title=reminder.text,
                payload=_reminder_item(reminder),
                followup_options=["查看提醒", "查看概览"],
            )
        if plan.action == "retry_failed_reminder":
            reminder = await self._retry_failed_reminder(plan, turn_context=turn_context)
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="reminder",
                object_id=reminder.reminder_id,
                object_title=reminder.text,
                payload=_reminder_item(reminder),
                followup_options=["查看失败提醒", "查看提醒"],
            )
        if plan.action == "create_memory":
            scope_object_type = None
            scope_object_id = None
            if plan.object_type in {"task", "reminder"}:
                resolved_scope = self.resolver.resolve(plan, turn_context=turn_context)
                if resolved_scope.status == "needs_disambiguation":
                    return AssistantDisambiguationResult(
                        prompt="你想把这条信息记到哪一个对象上？",
                        candidates=[
                            {
                                "object_type": candidate.object_type,
                                "object_id": candidate.object_id,
                                "title": candidate.title,
                            }
                            for candidate in resolved_scope.candidates
                        ],
                    )
                if resolved_scope.status == "needs_confirmation":
                    candidate = resolved_scope.candidates[0] if resolved_scope.candidates else None
                    return AssistantConfirmationResult(
                        prompt="我理解成你要把这条信息挂到这个对象上，先确认一下。",
                        confirm_action="create_memory",
                        preview_text=candidate.title if candidate is not None else None,
                    )
                if resolved_scope.object_type is not None:
                    plan = resolved_scope
                    scope_object_type = resolved_scope.object_type
                    scope_object_id = resolved_scope.object_id
            memory = await self.memory_service.create_memory(
                CreateMemoryCommand(
                    content=str(plan.args["content"]),
                    memory_type=_optional_str(plan.args.get("memory_type")),
                    conversation_id=turn_context.conversation_id,
                    session_id=turn_context.session_id,
                    source_channel=command.channel,
                    source_user_id=command.user_identity,
                    source_chat_id=command.chat_id,
                    source_thread_id=command.thread_id,
                    scope_object_type=scope_object_type,
                    scope_object_id=scope_object_id,
                )
            )
            return AssistantExecutionResult(
                success=True,
                action="create_memory",
                object_type="memory",
                object_id=memory.memory_id,
                object_title=memory.content,
                payload=_memory_item(memory),
                followup_options=["查看记忆", "归档这个记忆"],
            )
        if plan.action == "list_memories":
            memory_list = await self.memory_service.list_memories(
                ListMemoriesQuery(
                    conversation_id=turn_context.conversation_id,
                    session_id=turn_context.session_id,
                    status=_optional_str(plan.args.get("status")),
                    query=_optional_str(plan.args.get("query")),
                    limit=5,
                )
            )
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="memory",
                payload={
                    "status": _optional_str(plan.args.get("status")),
                    "query": _optional_str(plan.args.get("query")),
                    "items": [_memory_item(memory) for memory in memory_list.items],
                },
                followup_options=["归档第一个", "查看概览"],
            )
        if plan.action == "archive_memory":
            memory = await self._archive_memory(plan, turn_context=turn_context)
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="memory",
                object_id=memory.memory_id,
                object_title=memory.content,
                payload=_memory_item(memory),
                followup_options=["查看记忆", "查看概览"],
            )
        if plan.action == "convert_task_to_reminder":
            task = await self._get_task_from_plan(plan, turn_context=turn_context)
            reminder = await self.reminder_service.create_reminder(
                CreateReminderCommand(
                    text=_optional_str(plan.args.get("text")) or task.title,
                    remind_at=plan.args["remind_at"],
                    timezone=str(plan.args["timezone"]),
                    linked_task_id=task.task_id,
                    conversation_id=turn_context.conversation_id,
                    session_id=turn_context.session_id,
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
            await self.task_service.attach_reminder(
                task_id=task.task_id,
                reminder_id=reminder.reminder_id,
            )
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="task",
                object_id=task.task_id,
                object_title=task.title,
                payload={
                    "task": _task_item(task),
                    "reminder": _reminder_item(reminder),
                },
                followup_options=["查看提醒", "查看待办"],
            )
        if plan.action == "convert_reminder_to_task":
            reminder = await self._get_reminder_from_plan(plan, turn_context=turn_context)
            task = await self.task_service.create_task(
                CreateTaskCommand(
                    title=reminder.text,
                    linked_reminder_id=reminder.reminder_id,
                    source_type="reminder",
                    source_id=reminder.reminder_id,
                    conversation_id=turn_context.conversation_id,
                    session_id=turn_context.session_id,
                    source_channel=command.channel,
                    source_user_id=command.user_identity,
                    source_chat_id=command.chat_id,
                    source_thread_id=command.thread_id,
                )
            )
            await self.reminder_service.link_task(
                reminder_id=reminder.reminder_id,
                task_id=task.task_id,
            )
            if reminder.status == "pending":
                await self.reminder_service.cancel_reminder(
                    CancelReminderCommand(reminder_id=reminder.reminder_id)
                )
            return AssistantExecutionResult(
                success=True,
                action=plan.action,
                object_type="reminder",
                object_id=reminder.reminder_id,
                object_title=reminder.text,
                payload={
                    "task": _task_item(task),
                    "reminder": _reminder_item(reminder),
                },
                followup_options=["查看待办", "查看提醒"],
            )
        return None

    async def _complete_task(
        self,
        plan: AssistantActionPlan,
        *,
        turn_context: AssistantTurnContext,
    ) -> TaskDTO:
        reference_text = _optional_str(plan.args.get("reference_text"))
        if reference_text and hasattr(self.task_service, "complete_matching_task"):
            return await self.task_service.complete_matching_task(
                conversation_id=turn_context.conversation_id,
                session_id=turn_context.session_id,
                title_hint=reference_text,
            )
        if reference_text is None and hasattr(self.task_service, "complete_latest_task"):
            return await self.task_service.complete_latest_task(
                conversation_id=turn_context.conversation_id,
                session_id=turn_context.session_id,
            )
        assert plan.object_id is not None
        return await self.task_service.complete_task(CompleteTaskCommand(task_id=plan.object_id))

    async def _cancel_task(
        self,
        plan: AssistantActionPlan,
        *,
        turn_context: AssistantTurnContext,
    ) -> TaskDTO:
        reference_text = _optional_str(plan.args.get("reference_text"))
        if reference_text and hasattr(self.task_service, "cancel_matching_task"):
            return await self.task_service.cancel_matching_task(
                conversation_id=turn_context.conversation_id,
                session_id=turn_context.session_id,
                title_hint=reference_text,
            )
        if reference_text is None and hasattr(self.task_service, "cancel_latest_task"):
            return await self.task_service.cancel_latest_task(
                conversation_id=turn_context.conversation_id,
                session_id=turn_context.session_id,
            )
        assert plan.object_id is not None
        return await self.task_service.cancel_task(CancelTaskCommand(task_id=plan.object_id))

    async def _cancel_reminder(
        self,
        plan: AssistantActionPlan,
        *,
        turn_context: AssistantTurnContext,
    ) -> ReminderDTO:
        reference_text = _optional_str(plan.args.get("reference_text"))
        if reference_text and hasattr(self.reminder_service, "cancel_matching_reminder"):
            return await self.reminder_service.cancel_matching_reminder(
                conversation_id=turn_context.conversation_id,
                session_id=turn_context.session_id,
                text_hint=reference_text,
            )
        if reference_text is None and hasattr(self.reminder_service, "cancel_latest_reminder"):
            return await self.reminder_service.cancel_latest_reminder(
                conversation_id=turn_context.conversation_id,
                session_id=turn_context.session_id,
            )
        assert plan.object_id is not None
        return await self.reminder_service.cancel_reminder(
            CancelReminderCommand(reminder_id=plan.object_id)
        )

    async def _archive_memory(
        self,
        plan: AssistantActionPlan,
        *,
        turn_context: AssistantTurnContext,
    ) -> MemoryDTO:
        reference_text = _optional_str(plan.args.get("reference_text"))
        if reference_text and hasattr(self.memory_service, "archive_matching_memory"):
            return await self.memory_service.archive_matching_memory(
                conversation_id=turn_context.conversation_id,
                session_id=turn_context.session_id,
                content_hint=reference_text,
            )
        if reference_text is None and hasattr(self.memory_service, "archive_latest_memory"):
            return await self.memory_service.archive_latest_memory(
                conversation_id=turn_context.conversation_id,
                session_id=turn_context.session_id,
            )
        assert plan.object_id is not None
        return await self.memory_service.archive_memory(
            ArchiveMemoryCommand(memory_id=plan.object_id)
        )

    async def _retry_failed_reminder(
        self,
        plan: AssistantActionPlan,
        *,
        turn_context: AssistantTurnContext,
    ) -> ReminderDTO:
        assert plan.object_id is not None
        return await self.reminder_service.retry_failed_reminder(
            RetryFailedReminderCommand(reminder_id=plan.object_id)
        )

    async def _get_task_from_plan(
        self,
        plan: AssistantActionPlan,
        *,
        turn_context: AssistantTurnContext,
    ) -> TaskDTO:
        assert plan.object_id is not None
        return await self.task_service.get_task(plan.object_id)

    async def _get_reminder_from_plan(
        self,
        plan: AssistantActionPlan,
        *,
        turn_context: AssistantTurnContext,
    ) -> ReminderDTO:
        assert plan.object_id is not None
        return await self.reminder_service.get_reminder(plan.object_id)


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _task_item(task: TaskDTO) -> dict[str, str]:
    return {
        "object_type": "task",
        "object_id": task.task_id,
        "title": task.title,
        "status": task.status,
        "linked_reminder_id": task.linked_reminder_id or "",
    }


def _reminder_item(reminder: ReminderDTO) -> dict[str, str]:
    return {
        "object_type": "reminder",
        "object_id": reminder.reminder_id,
        "title": reminder.text,
        "status": reminder.status,
        "when": reminder.remind_at.isoformat(),
        "timezone": reminder.timezone,
        "linked_task_id": reminder.linked_task_id or "",
    }


def _memory_item(memory: MemoryDTO) -> dict[str, str]:
    return {
        "object_type": "memory",
        "object_id": memory.memory_id,
        "title": memory.content,
        "status": memory.status,
        "memory_type": memory.memory_type,
        "scope_object_type": memory.scope_object_type or "",
        "scope_object_id": memory.scope_object_id or "",
    }


def _focused_object_payload(turn_context: AssistantTurnContext) -> dict[str, str] | None:
    focused_object = turn_context.focused_object
    if focused_object is None:
        return None
    return {
        "object_type": focused_object.object_type,
        "object_id": focused_object.object_id,
        "title": focused_object.title or "",
    }


def _last_action_payload(turn_context: AssistantTurnContext) -> dict[str, str] | None:
    last_action = turn_context.last_assistant_action
    if last_action is None:
        return None
    return {
        "action_type": last_action.action_type,
        "summary": last_action.summary or "",
        "object_type": last_action.object_type or "",
        "object_id": last_action.object_id or "",
    }
