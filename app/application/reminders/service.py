from app.application.conversations.ports import ConversationContextResolver
from app.application.reminders.commands import (
    CancelReminderCommand,
    CreateReminderCommand,
    HandleReminderInboundMessageCommand,
    HandleReminderReplyCommand,
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
                limit=query.limit,
            )

        return ReminderListDTO(items=[self._to_dto(reminder) for reminder in reminders])

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

    async def handle_inbound_message(
        self,
        command: HandleReminderInboundMessageCommand,
    ) -> ReminderInboundMessageResult:
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


def _build_reminder_workflow_id(reminder_id: ReminderId) -> str:
    return f"reminder:{reminder_id.value}"
