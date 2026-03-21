from app.application.audit.service import AuditQueryService
from app.application.conversations.service import ConversationApplicationService
from app.application.reminders.service import ReminderApplicationService
from app.bootstrap.container import get_container
from app.infrastructure.integrations.messaging.feishu_webhook import FeishuWebhookHandler


def get_audit_service() -> AuditQueryService:
    return get_container().build_audit_service()


def get_conversation_service() -> ConversationApplicationService:
    return get_container().build_conversation_service()


def get_reminder_service() -> ReminderApplicationService:
    return get_container().build_reminder_service()


def get_feishu_webhook_handler() -> FeishuWebhookHandler:
    return get_container().build_feishu_webhook_handler()
