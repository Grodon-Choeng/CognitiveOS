import pytest

from app.application.audit.service import AuditQueryService
from app.application.conversations.service import ConversationApplicationService
from app.application.overview.service import OverviewApplicationService
from app.application.reminders.service import ReminderApplicationService
from app.bootstrap.container import create_runtime_container
from app.config.settings import Settings
from app.infrastructure.integrations.messaging.base import MessagingAdapter
from app.observability.message_events import MultiMessageEventRecorder


@pytest.mark.asyncio
async def test_runtime_container_reuses_app_scoped_singletons() -> None:
    container = create_runtime_container(
        Settings(
            feishu_app_id=None,
            feishu_app_secret=None,
        )
    )
    try:
        reminder_service = await container.get(ReminderApplicationService)
        conversation_service = await container.get(ConversationApplicationService)
        audit_service = await container.get(AuditQueryService)
        overview_service = await container.get(OverviewApplicationService)
        message_event_recorder = await container.get(MultiMessageEventRecorder)
        messaging_adapter = await container.get(MessagingAdapter)

        assert reminder_service is await container.get(ReminderApplicationService)
        assert conversation_service is await container.get(ConversationApplicationService)
        assert audit_service is await container.get(AuditQueryService)
        assert overview_service is await container.get(OverviewApplicationService)
        assert message_event_recorder is await container.get(MultiMessageEventRecorder)
        assert messaging_adapter is await container.get(MessagingAdapter)
        assert conversation_service.reminder_handler is not None
        assert conversation_service.turn_context_builder is not None
        assert conversation_service.turn_state_store is not None
        assert conversation_service.planner is not None
        assert conversation_service.executor is not None
        assert conversation_service.renderer is not None
    finally:
        await container.close()


@pytest.mark.asyncio
async def test_runtime_containers_are_isolated() -> None:
    first = create_runtime_container(Settings(feishu_app_id=None, feishu_app_secret=None))
    second = create_runtime_container(Settings(feishu_app_id=None, feishu_app_secret=None))
    try:
        assert await first.get(ReminderApplicationService) is not await second.get(
            ReminderApplicationService
        )
    finally:
        await first.close()
        await second.close()
