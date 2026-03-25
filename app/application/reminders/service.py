from app.application.conversations.ports import ConversationContextResolver
from app.application.reminders.commands import (
    CancelReminderCommand,
    CreateReminderCommand,
    HandleReminderInboundMessageCommand,
    HandleReminderReplyCommand,
    RescheduleReminderCommand,
    RetryFailedReminderCommand,
)
from app.application.reminders.dto import (
    ReminderDTO,
    ReminderInboundMessageResult,
    ReminderListDTO,
    ReminderReplyDTO,
)
from app.application.reminders.errors import (
    ReminderNotFoundError,
    ReminderStateConflictError,
    ReminderWorkflowCancelError,
    ReminderWorkflowNotStartedError,
    ReminderWorkflowStartError,
)
from app.application.reminders.matcher import ReminderInboundMatcher
from app.application.reminders.ports import (
    ReminderDispatchTarget,
    ReminderUnitOfWorkFactory,
    ReminderWorkflowGateway,
)
from app.application.reminders.queries import ListRemindersQuery
from app.domain.reminders.entities import Reminder, ReminderStatus
from app.domain.reminders.value_objects import ReminderId, ReminderSchedule

_REMINDER_REPLY_COMMAND_KEYWORDS = (
    "查看",
    "列出",
    "哪些",
    "几个",
    "现在都",
    "还有什么",
    "取消",
    "改到",
    "改成",
    "改期",
    "重试",
    "提醒我",
    "待办",
    "任务",
    "记忆",
    "概览",
)
_REMINDER_REPLY_ACK_PHRASES = (
    "收到",
    "收到提醒",
    "知道了",
    "我知道了",
    "完成了",
    "已完成",
    "处理好了",
    "已处理",
    "done",
)


class ReminderApplicationService:
    def __init__(
        self,
        unit_of_work_factory: ReminderUnitOfWorkFactory,
        workflow_gateway: ReminderWorkflowGateway,
        conversation_context_resolver: ConversationContextResolver,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.workflow_gateway = workflow_gateway
        self.conversation_context_resolver = conversation_context_resolver

    async def create_reminder(self, command: CreateReminderCommand) -> ReminderDTO:
        conversation_context = await self.conversation_context_resolver.resolve_for_outbound(
            provided_conversation_id=command.conversation_id,
            provided_session_id=command.session_id,
            source_channel=command.source_channel,
            source_user_id=command.source_user_id,
            source_chat_id=command.source_chat_id,
            source_thread_id=command.source_thread_id,
        )
        reminder = Reminder(
            reminder_id=ReminderId.new(),
            text=command.text,
            schedule=ReminderSchedule(
                remind_at=command.remind_at,
                timezone=command.timezone,
            ),
            conversation_id=conversation_context.conversation_id,
            session_id=conversation_context.session_id,
            dispatch_channel=command.dispatch_channel,
            dispatch_recipient_id=command.dispatch_recipient_id,
            dispatch_chat_id=command.dispatch_chat_id,
            dispatch_thread_id=command.dispatch_thread_id,
            linked_task_id=command.linked_task_id,
        )
        reminder.workflow_id = _build_reminder_workflow_id(reminder.reminder_id)

        async with self.unit_of_work_factory() as unit_of_work:
            await unit_of_work.reminders.add(reminder)
            await unit_of_work.commit()

        try:
            await self.workflow_gateway.start_reminder(
                reminder=reminder,
                dispatch_target=ReminderDispatchTarget(
                    channel=command.dispatch_channel,
                    recipient_id=command.dispatch_recipient_id,
                ),
            )
        except Exception as workflow_error:
            await self._mark_workflow_start_failed(reminder, workflow_error)
            raise ReminderWorkflowStartError(
                f"提醒工作流启动失败：{type(workflow_error).__name__}: {workflow_error}"
            ) from workflow_error

        return self._to_dto(reminder)

    async def handle_reply(self, command: HandleReminderReplyCommand) -> ReminderReplyDTO:
        reminder_id = ReminderId.from_string(command.reminder_id)

        async with self.unit_of_work_factory() as unit_of_work:
            reminder = await unit_of_work.reminders.get(reminder_id)
            if reminder is None:
                raise ReminderNotFoundError(f"提醒不存在：{command.reminder_id}")
            if reminder.status != ReminderStatus.PENDING:
                raise ReminderStateConflictError(f"提醒当前状态不允许回复：{reminder.status.value}")

            if reminder.workflow_id is None:
                raise ReminderWorkflowNotStartedError(f"提醒尚未启动工作流：{command.reminder_id}")

            await self.workflow_gateway.record_user_reply(
                workflow_id=reminder.workflow_id,
                reply_text=command.reply_text,
            )
            reminder.last_user_reply = command.reply_text
            reminder.status = ReminderStatus.COMPLETED
            await unit_of_work.reminders.update(reminder)
            await unit_of_work.commit()

        return ReminderReplyDTO(
            reminder_id=command.reminder_id,
            reply_text=command.reply_text,
            accepted=True,
            status=ReminderStatus.COMPLETED.value,
        )

    async def get_reminder(self, reminder_id: str) -> ReminderDTO:
        parsed_reminder_id = ReminderId.from_string(reminder_id)

        async with self.unit_of_work_factory() as unit_of_work:
            reminder = await unit_of_work.reminders.get(parsed_reminder_id)
            if reminder is None:
                raise ReminderNotFoundError(f"提醒不存在：{reminder_id}")

        return self._to_dto(reminder)

    async def list_reminders(self, query: ListRemindersQuery) -> ReminderListDTO:
        async with self.unit_of_work_factory() as unit_of_work:
            reminders = await unit_of_work.reminders.list(
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                status=query.status,
                query=query.query,
                limit=query.limit,
            )

        return ReminderListDTO(items=[self._to_dto(reminder) for reminder in reminders])

    async def find_candidates(
        self,
        *,
        conversation_id: str,
        session_id: str,
        query: str | None = None,
        status: str = ReminderStatus.PENDING.value,
        limit: int = 5,
    ) -> ReminderListDTO:
        return await self.list_reminders(
            ListRemindersQuery(
                conversation_id=conversation_id,
                session_id=session_id,
                status=status,
                query=query,
                limit=limit,
            )
        )

    async def reschedule_reminder(self, command: RescheduleReminderCommand) -> ReminderDTO:
        reminder_id = ReminderId.from_string(command.reminder_id)

        async with self.unit_of_work_factory() as unit_of_work:
            reminder = await unit_of_work.reminders.get(reminder_id)
            if reminder is None:
                raise ReminderNotFoundError(f"提醒不存在：{command.reminder_id}")
            if reminder.status not in {ReminderStatus.PENDING, ReminderStatus.FAILED}:
                raise ReminderStateConflictError(f"提醒当前状态不允许改期：{reminder.status.value}")

            if reminder.status == ReminderStatus.PENDING and reminder.workflow_id is not None:
                try:
                    await self.workflow_gateway.cancel_reminder(reminder.workflow_id)
                except Exception as workflow_error:
                    raise ReminderWorkflowCancelError(
                        f"提醒工作流取消失败：{type(workflow_error).__name__}: {workflow_error}"
                    ) from workflow_error

            reminder.text = command.text or reminder.text
            reminder.schedule = ReminderSchedule(
                remind_at=command.remind_at,
                timezone=command.timezone,
            )
            reminder.status = ReminderStatus.PENDING
            reminder.last_user_reply = None
            reminder.failure_stage = None
            reminder.failure_reason_code = None
            reminder.retryable = True
            reminder.workflow_id = reminder.workflow_id or _build_reminder_workflow_id(
                reminder.reminder_id
            )
            await unit_of_work.reminders.update(reminder)
            await unit_of_work.commit()

        try:
            await self.workflow_gateway.start_reminder(
                reminder=reminder,
                dispatch_target=ReminderDispatchTarget(
                    channel=reminder.dispatch_channel or "console",
                    recipient_id=reminder.dispatch_recipient_id or "local-user",
                ),
            )
        except Exception as workflow_error:
            await self._mark_workflow_start_failed(reminder, workflow_error)
            raise ReminderWorkflowStartError(
                f"提醒工作流重新启动失败：{type(workflow_error).__name__}: {workflow_error}"
            ) from workflow_error

        return self._to_dto(reminder)

    async def retry_failed_reminder(self, command: RetryFailedReminderCommand) -> ReminderDTO:
        reminder_id = ReminderId.from_string(command.reminder_id)

        async with self.unit_of_work_factory() as unit_of_work:
            reminder = await unit_of_work.reminders.get(reminder_id)
            if reminder is None:
                raise ReminderNotFoundError(f"提醒不存在：{command.reminder_id}")
            if reminder.status != ReminderStatus.FAILED:
                raise ReminderStateConflictError("只有失败提醒才能重试。")
            if not reminder.retryable:
                raise ReminderStateConflictError("当前失败提醒不可重试。")

            reminder.status = ReminderStatus.PENDING
            reminder.failure_stage = None
            reminder.failure_reason_code = None
            reminder.workflow_id = reminder.workflow_id or _build_reminder_workflow_id(
                reminder.reminder_id
            )
            await unit_of_work.reminders.update(reminder)
            await unit_of_work.commit()

        try:
            await self.workflow_gateway.start_reminder(
                reminder=reminder,
                dispatch_target=ReminderDispatchTarget(
                    channel=reminder.dispatch_channel or "console",
                    recipient_id=reminder.dispatch_recipient_id or "local-user",
                ),
            )
        except Exception as workflow_error:
            await self._mark_workflow_start_failed(reminder, workflow_error)
            raise ReminderWorkflowStartError(
                f"失败提醒重试失败：{type(workflow_error).__name__}: {workflow_error}"
            ) from workflow_error

        return self._to_dto(reminder)

    async def cancel_reminder(self, command: CancelReminderCommand) -> ReminderDTO:
        reminder_id = ReminderId.from_string(command.reminder_id)

        async with self.unit_of_work_factory() as unit_of_work:
            reminder = await unit_of_work.reminders.get(reminder_id)
            if reminder is None:
                raise ReminderNotFoundError(f"提醒不存在：{command.reminder_id}")

            if reminder.status == ReminderStatus.CANCELED:
                return self._to_dto(reminder)
            if reminder.status != ReminderStatus.PENDING:
                raise ReminderStateConflictError(f"提醒当前状态不允许取消：{reminder.status.value}")

            if reminder.workflow_id is not None:
                try:
                    await self.workflow_gateway.cancel_reminder(reminder.workflow_id)
                except Exception as workflow_error:
                    raise ReminderWorkflowCancelError(
                        f"提醒工作流取消失败：{type(workflow_error).__name__}: {workflow_error}"
                    ) from workflow_error

            reminder.status = ReminderStatus.CANCELED
            await unit_of_work.reminders.update(reminder)
            await unit_of_work.commit()

        return self._to_dto(reminder)

    async def cancel_latest_reminder(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ReminderDTO:
        reminder_list = await self.list_reminders(
            ListRemindersQuery(
                conversation_id=conversation_id,
                session_id=session_id,
                status=ReminderStatus.PENDING.value,
                limit=1,
            )
        )
        if not reminder_list.items:
            raise ReminderNotFoundError("当前会话没有可取消的提醒。")
        return await self.cancel_reminder(
            CancelReminderCommand(reminder_id=reminder_list.items[0].reminder_id)
        )

    async def cancel_matching_reminder(
        self,
        *,
        conversation_id: str,
        session_id: str,
        text_hint: str,
    ) -> ReminderDTO:
        reminder_list = await self.list_reminders(
            ListRemindersQuery(
                conversation_id=conversation_id,
                session_id=session_id,
                status=ReminderStatus.PENDING.value,
                limit=20,
            )
        )
        normalized_hint = text_hint.casefold()
        for reminder in reminder_list.items:
            if normalized_hint in reminder.text.casefold():
                return await self.cancel_reminder(
                    CancelReminderCommand(reminder_id=reminder.reminder_id)
                )
        raise ReminderNotFoundError(f"当前会话没有匹配“{text_hint}”的提醒。")

    async def link_task(
        self,
        *,
        reminder_id: str,
        task_id: str,
    ) -> ReminderDTO:
        parsed_reminder_id = ReminderId.from_string(reminder_id)

        async with self.unit_of_work_factory() as unit_of_work:
            reminder = await unit_of_work.reminders.get(parsed_reminder_id)
            if reminder is None:
                raise ReminderNotFoundError(f"提醒不存在：{reminder_id}")
            reminder.linked_task_id = task_id
            await unit_of_work.reminders.update(reminder)
            await unit_of_work.commit()

        return self._to_dto(reminder)

    async def handle_inbound_message(
        self,
        command: HandleReminderInboundMessageCommand,
    ) -> ReminderInboundMessageResult:
        if not _should_handle_as_reminder_reply(command.text):
            return ReminderInboundMessageResult(
                handled=False,
                reason="not_reminder_reply",
            )
        conversation_context = await self.conversation_context_resolver.resolve_for_inbound(
            source_channel=command.channel,
            source_user_id=command.sender_id,
            source_chat_id=command.chat_id,
            source_thread_id=command.thread_id,
        )
        command = HandleReminderInboundMessageCommand(
            conversation_id=conversation_context.conversation_id,
            session_id=conversation_context.session_id,
            channel=command.channel,
            sender_id=command.sender_id,
            message_id=command.message_id,
            root_message_id=command.root_message_id,
            parent_message_id=command.parent_message_id,
            chat_id=command.chat_id,
            thread_id=command.thread_id,
            text=command.text,
        )
        async with self.unit_of_work_factory() as unit_of_work:
            matcher = ReminderInboundMatcher(unit_of_work.reminders)
            reminder = await matcher.match(command)
            if reminder is None:
                return ReminderInboundMessageResult(
                    handled=False,
                    reason="no_pending_reminder",
                )

            if reminder.workflow_id is None:
                return ReminderInboundMessageResult(
                    handled=False,
                    reminder_id=str(reminder.reminder_id.value),
                    reason="workflow_not_started",
                )

            await self.workflow_gateway.record_user_reply(
                workflow_id=reminder.workflow_id,
                reply_text=command.text,
            )
            reminder.last_user_reply = command.text
            reminder.status = ReminderStatus.COMPLETED
            await unit_of_work.reminders.update(reminder)
            await unit_of_work.commit()

        return ReminderInboundMessageResult(
            handled=True,
            reminder_id=str(reminder.reminder_id.value),
        )

    @staticmethod
    def _to_dto(reminder: Reminder) -> ReminderDTO:
        return ReminderDTO(
            reminder_id=str(reminder.reminder_id.value),
            text=reminder.text,
            remind_at=reminder.schedule.remind_at,
            timezone=reminder.schedule.timezone,
            status=reminder.status.value,
            linked_task_id=reminder.linked_task_id,
            failure_stage=reminder.failure_stage,
            failure_reason_code=reminder.failure_reason_code,
            retryable=reminder.retryable,
            conversation_id=reminder.conversation_id,
            session_id=reminder.session_id,
            workflow_id=reminder.workflow_id,
        )

    async def _mark_workflow_start_failed(
        self,
        reminder: Reminder,
        workflow_error: Exception,
    ) -> None:
        reminder.status = ReminderStatus.FAILED
        reminder.workflow_id = None
        reminder.failure_stage = "workflow_start"
        reminder.failure_reason_code = type(workflow_error).__name__
        reminder.retryable = True

        try:
            async with self.unit_of_work_factory() as unit_of_work:
                await unit_of_work.reminders.update(reminder)
                await unit_of_work.commit()
        except Exception as persist_error:
            raise ReminderWorkflowStartError(
                "提醒工作流启动失败，且写回失败状态时发生错误："
                f"{type(workflow_error).__name__}: {workflow_error}；"
                f"{type(persist_error).__name__}: {persist_error}"
            ) from persist_error


def _should_handle_as_reminder_reply(text: str) -> bool:
    normalized = text.strip().casefold()
    if not normalized:
        return False
    if any(keyword in normalized for keyword in _REMINDER_REPLY_COMMAND_KEYWORDS):
        return False
    if normalized in _REMINDER_REPLY_ACK_PHRASES:
        return True
    if normalized.startswith(("我已经", "已经", "已")):
        return True
    return normalized.endswith("了")


def _build_reminder_workflow_id(reminder_id: ReminderId) -> str:
    return f"reminder:{reminder_id.value}"
