from temporalio.client import Client
from temporalio.worker import Worker

from app.config.settings import Settings
from app.infrastructure.integrations.messaging.base import MessagingAdapter
from app.infrastructure.temporal.activities.send_message import ReminderActivities
from app.infrastructure.temporal.workflows.reminder_workflow import ReminderWorkflow


def create_worker(
    client: Client,
    settings: Settings,
    messaging_adapter: MessagingAdapter,
) -> Worker:
    reminder_activities = ReminderActivities(messaging_adapter=messaging_adapter)
    return Worker(
        client=client,
        task_queue=settings.temporal_task_queue,
        workflows=[ReminderWorkflow],
        activities=[reminder_activities.send_reminder_message],
    )
