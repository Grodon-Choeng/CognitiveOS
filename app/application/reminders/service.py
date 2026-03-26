from app.application.conversations.ports import ConversationContextResolver
from app.application.reminders.commands import (
    CancelAllRemindersCommand,
    CancelReminderCommand,
    CreateReminderCommand,
    HandleReminderInboundMessageCommand,
    HandleReminderReplyCommand,
    RescheduleReminderCommand,
    RetryFailedReminderCommand,
)
from app.application.reminders.dto import (
    ReminderBulkCancelSummaryDTO,
    ReminderDTO,
    ReminderInboundMessageResult,
    ReminderListDTO,
    ReminderRecurrenceDTO,
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
from app.domain.reminders.value_objects import ReminderId, ReminderRecurrence, ReminderSchedule

_REMINDER_REPLY_PASS_TO_KERNEL_KEYWORDS = (
    "查看",
    "列出",
    "哪些",
    "几个",
    "现在都",
    "还有什么",
    "取消",
    "提醒我",
    "待办",
    "任务",
    "记忆",
    "概览",
)
_REMINDER_REPLY_RESCHEDULE_KEYWORDS = (
    "改到",
    "改成",
    "改期",
    "重试",
    "晚上再提醒",
    "明天再说",
    "明天提醒",
    "先别提醒",
)
_REMINDER_REPLY_ACK_PHRASES = (
    "收到",
    "收到提醒",
    "好的",
    "好",
    "知道了",
    "我知道了",
    "完成",
    "完成了",
    "已完成",
    "处理好了",
    "已处理",
    "done",
)
_REMINDER_REPLY_REJECT_PHRASES = ("不是这个", "先不用", "不用了", "不相关", "你说啥")
_REMINDER_REPLY_FOLLOWUP_REFERENCE_PHRASES = ("另一个", "第二个", "上一个", "刚才那个", "这个")
_MALFORMED_REMINDER_CONNECTORS = ("然后", "也得", "另行通知", "其他非工作日", "并且", "同时")


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
                recurrence=command.recurrence,
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
        reply_semantics = _classify_reminder_reply_semantics(command.reply_text)

        if reply_semantics != "acknowledge":
            return ReminderReplyDTO(
                reminder_id=command.reminder_id,
                reply_text=command.reply_text,
                accepted=False,
                status=ReminderStatus.PENDING.value,
            )

        async with self.unit_of_work_factory() as unit_of_work:
            reminder = await unit_of_work.reminders.get(reminder_id)
            if reminder is None:
                raise ReminderNotFoundError(f"提醒不存在：{command.reminder_id}")
            if reminder.schedule.is_recurring:
                return ReminderReplyDTO(
                    reminder_id=command.reminder_id,
                    reply_text=command.reply_text,
                    accepted=False,
                    status=ReminderStatus.PENDING.value,
                )
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
        if query.status in {None, ReminderStatus.PENDING.value}:
            return await self.list_active_reminders(query)

        async with self.unit_of_work_factory() as unit_of_work:
            reminders = await unit_of_work.reminders.list(
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                status=query.status,
                query=query.query,
                limit=query.limit,
            )

        return ReminderListDTO(items=[self._to_dto(reminder) for reminder in reminders])

    async def list_active_reminders(self, query: ListRemindersQuery) -> ReminderListDTO:
        async with self.unit_of_work_factory() as unit_of_work:
            reminders = await unit_of_work.reminders.list(
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                status=ReminderStatus.PENDING.value,
                query=query.query,
                limit=max(query.limit * 3, query.limit),
            )

        visible_reminders = [
            reminder for reminder in reminders if not _is_hidden_active_reminder(reminder)
        ]
        return ReminderListDTO(
            items=[self._to_dto(reminder) for reminder in visible_reminders[: query.limit]]
        )

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

    async def list_recent_pending(
        self,
        *,
        conversation_id: str,
        session_id: str,
        limit: int = 5,
    ) -> ReminderListDTO:
        """提供中性 working set 查询，供 resolver / turn context 读取。"""
        return await self.find_candidates(
            conversation_id=conversation_id,
            session_id=session_id,
            status=ReminderStatus.PENDING.value,
            limit=limit,
        )

    async def cancel_all_reminders(
        self,
        command: CancelAllRemindersCommand,
    ) -> ReminderBulkCancelSummaryDTO:
        if command.conversation_id is None and command.session_id is None:
            raise ReminderStateConflictError("批量取消提醒时必须提供会话范围。")

        active_reminders = await self.list_active_reminders(
            ListRemindersQuery(
                conversation_id=command.conversation_id,
                session_id=command.session_id,
                limit=500,
            )
        )
        if not active_reminders.items:
            return ReminderBulkCancelSummaryDTO(
                total_canceled=0,
                one_off_canceled=0,
                recurring_canceled=0,
                canceled_items=[],
            )

        canceled_items: list[ReminderDTO] = []
        for reminder in active_reminders.items:
            canceled_items.append(
                await self.cancel_reminder(CancelReminderCommand(reminder_id=reminder.reminder_id))
            )

        recurring_canceled = sum(1 for item in canceled_items if item.recurrence is not None)
        one_off_canceled = len(canceled_items) - recurring_canceled
        return ReminderBulkCancelSummaryDTO(
            total_canceled=len(canceled_items),
            one_off_canceled=one_off_canceled,
            recurring_canceled=recurring_canceled,
            canceled_items=canceled_items,
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
        reply_semantics = _classify_reminder_reply_semantics(command.text)
        if reply_semantics == "pass_to_kernel":
            return ReminderInboundMessageResult(
                handled=False,
                reason="not_reminder_reply",
                decision="pass_to_kernel",
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
            matched = await matcher.match(command)
            if matched is None:
                return ReminderInboundMessageResult(
                    handled=False,
                    reason="no_pending_reminder",
                    decision="pass_to_kernel",
                )

            reminder = matched.reminder
            if reminder.schedule.is_recurring:
                return ReminderInboundMessageResult(
                    handled=False,
                    reminder_id=str(reminder.reminder_id.value),
                    reason="recurring_reminder_reply_not_supported",
                    decision="pass_to_kernel",
                    match_source=matched.source,
                )
            if reply_semantics == "reject_or_not_related":
                return ReminderInboundMessageResult(
                    handled=False,
                    reminder_id=str(reminder.reminder_id.value),
                    reason="reminder_reply_rejected",
                    decision="pass_to_kernel",
                    match_source=matched.source,
                )

            if reply_semantics == "reschedule_or_defer":
                return ReminderInboundMessageResult(
                    handled=False,
                    reminder_id=str(reminder.reminder_id.value),
                    reason="reminder_followup_needs_confirmation",
                    response_text="我先不把这条提醒记成完成。你像是在说要调整刚才那条提醒，如果是它，可以直接继续说“改这条到明天下午”或“先别提醒”。",
                    decision="needs_confirmation",
                    match_source=matched.source,
                )

            if matched.confidence != "high":
                return ReminderInboundMessageResult(
                    handled=False,
                    reminder_id=str(reminder.reminder_id.value),
                    reason="reminder_match_low_confidence",
                    response_text="我理解成你可能是在回复最近这条提醒，但这一步我不自动完成。你可以直接说“就是这条提醒”，或者把要改的内容再说完整一点。",
                    decision="needs_confirmation",
                    match_source=matched.source,
                )

            if reminder.workflow_id is None:
                return ReminderInboundMessageResult(
                    handled=False,
                    reminder_id=str(reminder.reminder_id.value),
                    reason="workflow_not_started",
                    decision="pass_to_kernel",
                    match_source=matched.source,
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
            reason="reminder_replied",
            response_text="好的，这条提醒我帮你记为已收到。",
            decision="completed",
            match_source=matched.source,
        )

    @staticmethod
    def _to_dto(reminder: Reminder) -> ReminderDTO:
        return ReminderDTO(
            reminder_id=str(reminder.reminder_id.value),
            text=reminder.text,
            remind_at=reminder.schedule.remind_at,
            timezone=reminder.schedule.timezone,
            status=reminder.status.value,
            recurrence=_to_recurrence_dto(reminder.schedule.recurrence),
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


def _classify_reminder_reply_semantics(text: str) -> str:
    normalized = text.strip().casefold()
    if not normalized:
        return "pass_to_kernel"
    if any(keyword in normalized for keyword in _REMINDER_REPLY_PASS_TO_KERNEL_KEYWORDS):
        return "pass_to_kernel"
    if any(keyword in normalized for keyword in _REMINDER_REPLY_RESCHEDULE_KEYWORDS):
        return "reschedule_or_defer"
    if any(phrase in normalized for phrase in _REMINDER_REPLY_REJECT_PHRASES):
        if any(phrase in normalized for phrase in _REMINDER_REPLY_FOLLOWUP_REFERENCE_PHRASES):
            return "pass_to_kernel"
        return "reject_or_not_related"
    if normalized in _REMINDER_REPLY_ACK_PHRASES:
        return "acknowledge"
    if normalized.startswith(("我已经", "已经", "已")):
        return "acknowledge"
    return "pass_to_kernel"


def _build_reminder_workflow_id(reminder_id: ReminderId) -> str:
    return f"reminder:{reminder_id.value}"


def _to_recurrence_dto(recurrence: ReminderRecurrence | None) -> ReminderRecurrenceDTO | None:
    if recurrence is None:
        return None
    return ReminderRecurrenceDTO(
        recurrence_type=recurrence.recurrence_type,
        weekdays=list(recurrence.weekdays),
        hour=recurrence.hour,
        minute=recurrence.minute,
    )


def _is_hidden_active_reminder(reminder: Reminder) -> bool:
    normalized = reminder.text.strip()
    if not normalized:
        return True
    if "另行通知" in normalized:
        return True
    if len(normalized) >= 80:
        return True
    connector_hits = sum(1 for keyword in _MALFORMED_REMINDER_CONNECTORS if keyword in normalized)
    if normalized.count("提醒") >= 2 and connector_hits >= 1 and len(normalized) >= 24:
        return True
    if connector_hits >= 2 and len(normalized) >= 20:
        return True
    return False
