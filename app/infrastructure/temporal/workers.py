from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.client import Client
from temporalio.worker import Worker

from app.config.settings import Settings
from app.infrastructure.integrations.messaging.base import MessagingAdapter
from app.infrastructure.temporal.activities.send_message import ReminderActivities
from app.infrastructure.temporal.workflows.reminder_workflow import ReminderWorkflow
from app.observability.workflow_events import WorkflowEventRecorder


def create_worker(
    client: Client,
    settings: Settings,
    messaging_adapter: MessagingAdapter,
    session_factory: async_sessionmaker[AsyncSession],
    workflow_event_recorder: WorkflowEventRecorder,
) -> Worker:
    reminder_activities = ReminderActivities(
        messaging_adapter=messaging_adapter,
        session_factory=session_factory,
        workflow_event_recorder=workflow_event_recorder,
    )
    return Worker(
        client=client,
        task_queue=settings.temporal_task_queue,
        workflows=[ReminderWorkflow],
        activities=[
            reminder_activities.send_reminder_message,
            reminder_activities.record_dispatch_message_id,
        ],
    )
