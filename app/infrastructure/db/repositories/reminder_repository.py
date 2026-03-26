from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.reminders.entities import Reminder, ReminderStatus
from app.domain.reminders.repository import ReminderRepository
from app.domain.reminders.value_objects import ReminderId, ReminderRecurrence, ReminderSchedule
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

    async def list(
        self,
        *,
        conversation_id: str | None = None,
        session_id: str | None = None,
        status: str | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> list[Reminder]:
        statement = select(ReminderModel).order_by(ReminderModel.created_at.desc()).limit(limit)
        if conversation_id is not None:
            statement = statement.where(ReminderModel.conversation_id == conversation_id)
        if session_id is not None:
            statement = statement.where(ReminderModel.session_id == session_id)
        if status is not None:
            statement = statement.where(ReminderModel.status == status)
        if query is not None:
            statement = statement.where(ReminderModel.text.ilike(f"%{query}%"))

        models = (await self.session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    async def get_by_dispatch_message_id(self, dispatch_message_id: str) -> Reminder | None:
        statement = (
            select(ReminderModel)
            .where(ReminderModel.dispatch_message_id == dispatch_message_id)
            .limit(1)
        )
        result = await self.session.execute(statement)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_domain(model)

    async def get_latest_pending_by_conversation(
        self,
        conversation_id: str,
    ) -> Reminder | None:
        statement = (
            select(ReminderModel)
            .where(ReminderModel.status == ReminderStatus.PENDING.value)
            .where(ReminderModel.conversation_id == conversation_id)
            .order_by(ReminderModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(statement)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_domain(model)

    async def get_latest_pending_by_dispatch_chat(
        self,
        channel: str,
        recipient_id: str,
        chat_id: str,
        thread_id: str | None = None,
    ) -> Reminder | None:
        statement = (
            select(ReminderModel)
            .where(ReminderModel.status == ReminderStatus.PENDING.value)
            .where(ReminderModel.dispatch_channel == channel)
            .where(ReminderModel.dispatch_recipient_id == recipient_id)
            .where(ReminderModel.dispatch_chat_id == chat_id)
        )
        if thread_id is None:
            statement = statement.where(ReminderModel.dispatch_thread_id.is_(None))
        else:
            statement = statement.where(ReminderModel.dispatch_thread_id == thread_id)

        statement = statement.order_by(ReminderModel.created_at.desc()).limit(1)
        result = await self.session.execute(statement)
        model = result.scalar_one_or_none()

        if model is None:
            return None

        return self._to_domain(model)

    async def get_latest_pending_by_dispatch(
        self,
        channel: str,
        recipient_id: str,
    ) -> Reminder | None:
        statement = (
            select(ReminderModel)
            .where(ReminderModel.status == ReminderStatus.PENDING.value)
            .where(ReminderModel.dispatch_channel == channel)
            .where(ReminderModel.dispatch_recipient_id == recipient_id)
            .order_by(ReminderModel.created_at.desc())
            .limit(1)
        )
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
        model.recurrence_json = _recurrence_to_json(reminder.schedule.recurrence)
        model.status = reminder.status.value
        model.workflow_id = reminder.workflow_id
        model.conversation_id = reminder.conversation_id
        model.session_id = reminder.session_id
        model.dispatch_channel = reminder.dispatch_channel
        model.dispatch_recipient_id = reminder.dispatch_recipient_id
        model.dispatch_chat_id = reminder.dispatch_chat_id
        model.dispatch_thread_id = reminder.dispatch_thread_id
        model.dispatch_message_id = reminder.dispatch_message_id
        model.last_user_reply = reminder.last_user_reply
        model.linked_task_id = reminder.linked_task_id
        model.failure_stage = reminder.failure_stage
        model.failure_reason_code = reminder.failure_reason_code
        model.retryable = reminder.retryable

    @staticmethod
    def _to_model(reminder: Reminder) -> ReminderModel:
        return ReminderModel(
            id=str(reminder.reminder_id.value),
            text=reminder.text,
            remind_at=reminder.schedule.remind_at,
            timezone=reminder.schedule.timezone,
            recurrence_json=_recurrence_to_json(reminder.schedule.recurrence),
            status=reminder.status.value,
            workflow_id=reminder.workflow_id,
            conversation_id=reminder.conversation_id,
            session_id=reminder.session_id,
            dispatch_channel=reminder.dispatch_channel,
            dispatch_recipient_id=reminder.dispatch_recipient_id,
            dispatch_chat_id=reminder.dispatch_chat_id,
            dispatch_thread_id=reminder.dispatch_thread_id,
            dispatch_message_id=reminder.dispatch_message_id,
            last_user_reply=reminder.last_user_reply,
            linked_task_id=reminder.linked_task_id,
            failure_stage=reminder.failure_stage,
            failure_reason_code=reminder.failure_reason_code,
            retryable=reminder.retryable,
        )

    @staticmethod
    def _to_domain(model: ReminderModel) -> Reminder:
        return Reminder(
            reminder_id=ReminderId.from_string(model.id),
            text=model.text,
            schedule=ReminderSchedule(
                remind_at=model.remind_at,
                timezone=model.timezone,
                recurrence=_recurrence_from_json(model.recurrence_json),
            ),
            status=ReminderStatus(model.status),
            workflow_id=model.workflow_id,
            conversation_id=model.conversation_id,
            session_id=model.session_id,
            dispatch_channel=model.dispatch_channel,
            dispatch_recipient_id=model.dispatch_recipient_id,
            dispatch_chat_id=model.dispatch_chat_id,
            dispatch_thread_id=model.dispatch_thread_id,
            dispatch_message_id=model.dispatch_message_id,
            last_user_reply=model.last_user_reply,
            linked_task_id=model.linked_task_id,
            failure_stage=model.failure_stage,
            failure_reason_code=model.failure_reason_code,
            retryable=model.retryable,
        )


def _recurrence_to_json(recurrence: ReminderRecurrence | None) -> dict[str, object] | None:
    if recurrence is None:
        return None
    return recurrence.to_payload()


def _recurrence_from_json(payload: object) -> ReminderRecurrence | None:
    if not isinstance(payload, dict):
        return None
    return ReminderRecurrence.from_payload(payload)
