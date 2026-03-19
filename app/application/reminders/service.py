from app.application.reminders.commands import CreateReminderCommand, HandleReminderReplyCommand
from app.application.reminders.dto import ReminderDTO, ReminderReplyDTO
from app.application.reminders.errors import ReminderNotFoundError, ReminderWorkflowNotStartedError
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
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.workflow_gateway = workflow_gateway

    async def create_reminder(self, command: CreateReminderCommand) -> ReminderDTO:
        reminder = Reminder(
            reminder_id=ReminderId.new(),
            text=command.text,
            schedule=ReminderSchedule(
                remind_at=command.remind_at,
                timezone=command.timezone,
            ),
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
                raise ReminderWorkflowNotStartedError(
                    f"提醒尚未启动工作流：{command.reminder_id}"
                )

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

    def _to_dto(self, reminder: Reminder) -> ReminderDTO:
        return ReminderDTO(
            reminder_id=str(reminder.reminder_id.value),
            text=reminder.text,
            remind_at=reminder.schedule.remind_at,
            timezone=reminder.schedule.timezone,
            status=reminder.status.value,
            workflow_id=reminder.workflow_id,
        )
