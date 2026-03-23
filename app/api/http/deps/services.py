from dishka.integrations.fastapi import FromDishka, inject

from app.application.audit.service import AuditQueryService
from app.application.conversations.service import ConversationApplicationService
from app.application.memory.service import MemoryApplicationService
from app.application.overview.service import OverviewApplicationService
from app.application.reminders.service import ReminderApplicationService
from app.application.tasks.service import TaskApplicationService
from app.infrastructure.integrations.messaging.feishu_webhook import FeishuWebhookHandler


@inject
def get_audit_service(service: FromDishka[AuditQueryService]) -> AuditQueryService:
    return service


@inject
def get_conversation_service(
    service: FromDishka[ConversationApplicationService],
) -> ConversationApplicationService:
    return service


@inject
def get_reminder_service(
    service: FromDishka[ReminderApplicationService],
) -> ReminderApplicationService:
    return service


@inject
def get_memory_service(service: FromDishka[MemoryApplicationService]) -> MemoryApplicationService:
    return service


@inject
def get_task_service(service: FromDishka[TaskApplicationService]) -> TaskApplicationService:
    return service


@inject
def get_overview_service(
    service: FromDishka[OverviewApplicationService],
) -> OverviewApplicationService:
    return service


@inject
def get_feishu_webhook_handler(
    handler: FromDishka[FeishuWebhookHandler],
) -> FeishuWebhookHandler:
    return handler
