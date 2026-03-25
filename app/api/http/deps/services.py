from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends

from app.application.audit.service import AuditQueryService
from app.application.conversations.service import ConversationApplicationService
from app.application.debug_im.service import DebugIMApplicationService
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
async def get_debug_im_service(
    service: FromDishka[DebugIMApplicationService],
) -> DebugIMApplicationService:
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


AuditServiceDep = Annotated[AuditQueryService, Depends(get_audit_service)]
ConversationServiceDep = Annotated[
    ConversationApplicationService,
    Depends(get_conversation_service),
]
DebugIMServiceDep = Annotated[DebugIMApplicationService, Depends(get_debug_im_service)]
ReminderServiceDep = Annotated[ReminderApplicationService, Depends(get_reminder_service)]
MemoryServiceDep = Annotated[MemoryApplicationService, Depends(get_memory_service)]
TaskServiceDep = Annotated[TaskApplicationService, Depends(get_task_service)]
OverviewServiceDep = Annotated[OverviewApplicationService, Depends(get_overview_service)]
FeishuWebhookHandlerDep = Annotated[
    FeishuWebhookHandler,
    Depends(get_feishu_webhook_handler),
]
