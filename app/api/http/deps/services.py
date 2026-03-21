from app.application.reminders.service import ReminderApplicationService
from app.bootstrap.container import get_container
from app.infrastructure.integrations.messaging.feishu_webhook import FeishuWebhookHandler


def get_reminder_service() -> ReminderApplicationService:
    return get_container().build_reminder_service()


def get_feishu_webhook_handler() -> FeishuWebhookHandler:
    return get_container().build_feishu_webhook_handler()
