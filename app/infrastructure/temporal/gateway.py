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
from app.observability.context import current_trace_fields
from app.observability.workflow_events import WorkflowEventRecord, WorkflowEventRecorder


class TemporalReminderWorkflowGateway(ReminderWorkflowGateway):
    def __init__(
        self,
        settings: Settings,
        workflow_event_recorder: WorkflowEventRecorder,
    ) -> None:
        self.settings = settings
        self.workflow_event_recorder = workflow_event_recorder
        self._client: Client | None = None
        self._client_lock = asyncio.Lock()

    async def start_reminder(
        self,
        reminder: Reminder,
        dispatch_target: ReminderDispatchTarget,
    ) -> str:
        client = await self._get_client()
        workflow_id = reminder.workflow_id or _build_workflow_id(reminder)
        start_delay = self._build_start_delay(reminder.schedule.remind_at)
        trace_id, chain_id, request_id = current_trace_fields()

        try:
            await client.start_workflow(
                self.settings.temporal_reminder_workflow_name,
                ReminderWorkflowInput(
                    reminder_id=str(reminder.reminder_id.value),
                    text=reminder.text,
                    remind_at=reminder.schedule.remind_at.isoformat(),
                    timezone=reminder.schedule.timezone,
                    recurrence=(
                        reminder.schedule.recurrence.to_payload()
                        if reminder.schedule.recurrence is not None
                        else None
                    ),
                    conversation_id=reminder.conversation_id,
                    session_id=reminder.session_id,
                    trace_id=trace_id,
                    chain_id=chain_id,
                    request_id=request_id,
                    dispatch_channel=dispatch_target.channel,
                    dispatch_recipient_id=dispatch_target.recipient_id,
                    dispatch_chat_id=reminder.dispatch_chat_id,
                    dispatch_thread_id=reminder.dispatch_thread_id,
                ),
                id=workflow_id,
                task_queue=self.settings.temporal_task_queue,
                start_delay=start_delay,
            )
        except Exception as exc:
            await self.workflow_event_recorder.record(
                WorkflowEventRecord.create(
                    workflow_id=workflow_id,
                    workflow_type=self.settings.temporal_reminder_workflow_name,
                    event_type="workflow_start_failed",
                    conversation_id=reminder.conversation_id,
                    session_id=reminder.session_id,
                    trace_id=trace_id,
                    chain_id=chain_id,
                    request_id=request_id,
                    success=False,
                    message="提醒工作流启动失败。",
                    payload={
                        "reminder_id": str(reminder.reminder_id.value),
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    },
                )
            )
            raise
        await self.workflow_event_recorder.record(
            WorkflowEventRecord.create(
                workflow_id=workflow_id,
                workflow_type=self.settings.temporal_reminder_workflow_name,
                event_type="workflow_started",
                conversation_id=reminder.conversation_id,
                session_id=reminder.session_id,
                trace_id=trace_id,
                chain_id=chain_id,
                request_id=request_id,
                message="提醒工作流已启动。",
                payload={"reminder_id": str(reminder.reminder_id.value)},
            )
        )
        return workflow_id

    async def record_user_reply(self, workflow_id: str, reply_text: str) -> None:
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(RECORD_USER_REPLY_SIGNAL, reply_text)
        trace_id, chain_id, request_id = current_trace_fields()
        await self.workflow_event_recorder.record(
            WorkflowEventRecord.create(
                workflow_id=workflow_id,
                workflow_type=self.settings.temporal_reminder_workflow_name,
                event_type="reply_signal_sent",
                conversation_id=None,
                session_id=None,
                trace_id=trace_id,
                chain_id=chain_id,
                request_id=request_id,
                message="已向工作流发送回复信号。",
                payload={"reply_text": reply_text},
            )
        )

    async def cancel_reminder(self, workflow_id: str) -> None:
        client = await self._get_client()
        handle = client.get_workflow_handle(workflow_id)
        await handle.cancel()
        trace_id, chain_id, request_id = current_trace_fields()
        await self.workflow_event_recorder.record(
            WorkflowEventRecord.create(
                workflow_id=workflow_id,
                workflow_type=self.settings.temporal_reminder_workflow_name,
                event_type="workflow_cancel_requested",
                conversation_id=None,
                session_id=None,
                trace_id=trace_id,
                chain_id=chain_id,
                request_id=request_id,
                message="已向工作流发送取消请求。",
                payload={},
            )
        )

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


def _build_workflow_id(reminder: Reminder) -> str:
    return f"reminder:{reminder.reminder_id.value}"
