import asyncio
from datetime import UTC, datetime, timedelta

from temporalio.client import Client

from app.application.reminders.ports import (
    ReminderDispatchTarget,
    ReminderWorkflowGateway,
)
from app.config.settings import Settings
from app.domain.reminders.entities import Reminder
from app.infrastructure.temporal.client import create_temporal_client
from app.infrastructure.temporal.workflows.reminder_workflow import (
    RECORD_USER_REPLY_SIGNAL,
    ReminderWorkflowInput,
)


class TemporalReminderWorkflowGateway(ReminderWorkflowGateway):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Client | None = None
        self._client_lock = asyncio.Lock()

    async def start_reminder(
        self,
        reminder: Reminder,
        dispatch_target: ReminderDispatchTarget,
    ) -> str:
        client = await self._get_client()
        workflow_id = f"reminder:{reminder.reminder_id.value}"
        start_delay = self._build_start_delay(reminder.schedule.remind_at)

        await client.start_workflow(
            self.settings.temporal_reminder_workflow_name,
            ReminderWorkflowInput(
                reminder_id=str(reminder.reminder_id.value),
                text=reminder.text,
                remind_at=reminder.schedule.remind_at.isoformat(),
                timezone=reminder.schedule.timezone,
                dispatch_channel=dispatch_target.channel,
                dispatch_recipient_id=dispatch_target.recipient_id,
            ),
            id=workflow_id,
            task_queue=self.settings.temporal_task_queue,
            start_delay=start_delay,
        )
        return workflow_id

    async def record_user_reply(self, workflow_id: str, reply_text: str) -> None:
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(RECORD_USER_REPLY_SIGNAL, reply_text)

    async def _get_client(self) -> Client:
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    self._client = await create_temporal_client(self.settings)
        return self._client

    @staticmethod
    def _build_start_delay(remind_at: datetime) -> timedelta | None:
        normalized_remind_at = remind_at
        if normalized_remind_at.tzinfo is None:
            normalized_remind_at = normalized_remind_at.replace(tzinfo=UTC)

        delay = normalized_remind_at - datetime.now(UTC)
        if delay <= timedelta(0):
            return None
        return delay
