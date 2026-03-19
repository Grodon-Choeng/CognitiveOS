from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.reminders.entities import Reminder, ReminderStatus
from app.domain.reminders.repository import ReminderRepository
from app.domain.reminders.value_objects import ReminderId, ReminderSchedule
from app.infrastructure.db.models.reminder import ReminderModel


class SQLAlchemyReminderRepository(ReminderRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, reminder: Reminder) -> None:
        self.session.add(self._to_model(reminder))

    async def get(self, reminder_id: ReminderId) -> Reminder | None:
        statement = select(ReminderModel).where(ReminderModel.id == str(reminder_id.value))
        result = await self.session.execute(statement)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_domain(model)

    async def update(self, reminder: Reminder) -> None:
        model = await self.session.get(ReminderModel, str(reminder.reminder_id.value))
        if model is None:
            self.session.add(self._to_model(reminder))
            return

        model.text = reminder.text
        model.remind_at = reminder.schedule.remind_at
        model.timezone = reminder.schedule.timezone
        model.status = reminder.status.value
        model.workflow_id = reminder.workflow_id
        model.last_user_reply = reminder.last_user_reply

    @staticmethod
    def _to_model(reminder: Reminder) -> ReminderModel:
        return ReminderModel(
            id=str(reminder.reminder_id.value),
            text=reminder.text,
            remind_at=reminder.schedule.remind_at,
            timezone=reminder.schedule.timezone,
            status=reminder.status.value,
            workflow_id=reminder.workflow_id,
            last_user_reply=reminder.last_user_reply,
        )

    @staticmethod
    def _to_domain(model: ReminderModel) -> Reminder:
        return Reminder(
            reminder_id=ReminderId.from_string(model.id),
            text=model.text,
            schedule=ReminderSchedule(
                remind_at=model.remind_at,
                timezone=model.timezone,
            ),
            status=ReminderStatus(model.status),
            workflow_id=model.workflow_id,
            last_user_reply=model.last_user_reply,
        )
