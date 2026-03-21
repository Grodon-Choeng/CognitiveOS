from app.application.conversations.ports import ConversationContextResolver
from app.application.reminders.commands import (
    CreateReminderCommand,
    HandleReminderInboundMessageCommand,
    HandleReminderReplyCommand,
)
from app.application.reminders.dto import (
    ReminderDTO,
    ReminderInboundMessageResult,
    ReminderReplyDTO,
)
from app.application.reminders.errors import ReminderNotFoundError, ReminderWorkflowNotStartedError
from app.application.reminders.matcher import ReminderInboundMatcher
from app.application.reminders.ports import (
    ReminderDispatchTarget,
    ReminderUnitOfWorkFactory,
    ReminderWorkflowGateway,
)
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

        async with self.unit_of_work_factory() as unit_of_work:
            await unit_of_work.reminders.add(reminder)
            await unit_of_work.commit()

        workflow_id = await self.workflow_gateway.start_reminder(
            reminder=reminder,
            dispatch_target=ReminderDispatchTarget(
                channel=command.dispatch_channel,
                recipient_id=command.dispatch_recipient_id,
            ),
        )

        reminder.workflow_id = workflow_id

        async with self.unit_of_work_factory() as unit_of_work:
            await unit_of_work.reminders.update(reminder)
            await unit_of_work.commit()

        return self._to_dto(reminder)

    async def handle_reply(self, command: HandleReminderReplyCommand) -> ReminderReplyDTO:
        reminder_id = ReminderId.from_string(command.reminder_id)

        async with self.unit_of_work_factory() as unit_of_work:
            reminder = await unit_of_work.reminders.get(reminder_id)
            if reminder is None:
                raise ReminderNotFoundError(f"提醒不存在：{command.reminder_id}")

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
