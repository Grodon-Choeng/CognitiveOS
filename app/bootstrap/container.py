from functools import lru_cache

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.application.audit.service import AuditQueryService
from app.application.conversations.handlers import ConversationInboundHandler
from app.application.conversations.ports import ConversationContextResolver
from app.application.conversations.service import ConversationApplicationService
from app.application.reminders.conversation_handler import ReminderConversationHandler
from app.application.reminders.ports import ReminderUnitOfWorkFactory
from app.application.reminders.service import ReminderApplicationService
from app.bootstrap.inbound_events import ConversationInboundEventRecorder
from app.config.settings import Settings, get_settings
from app.infrastructure.conversations import SqlAlchemyConversationContextResolver
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.db.uow import SQLAlchemyReminderUnitOfWork
from app.infrastructure.integrations.messaging import (
    FeishuLongConnectionListener,
    FeishuMessagingAdapter,
    FeishuWebhookHandler,
    LoggingMessagingAdapter,
    MessagingAdapter,
    RecordingMessagingAdapter,
    RoutingMessagingAdapter,
)
from app.infrastructure.temporal.gateway import TemporalReminderWorkflowGateway
from app.observability.message_events import (
    DatabaseMessageEventRecorder,
    JsonlMessageEventRecorder,
    MultiMessageEventRecorder,
)
from app.observability.model_invocations import (
    DatabaseModelInvocationRecorder,
    JsonlModelInvocationRecorder,
    MultiModelInvocationRecorder,
)
from app.observability.tool_invocations import (
    DatabaseToolInvocationRecorder,
    JsonlToolInvocationRecorder,
    MultiToolInvocationRecorder,
)
from app.observability.workflow_events import (
    DatabaseWorkflowEventRecorder,
    JsonlWorkflowEventRecorder,
    MultiWorkflowEventRecorder,
)


class ApplicationContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session_factory: async_sessionmaker = get_session_factory(settings)
        self.workflow_gateway = TemporalReminderWorkflowGateway(
            settings=settings,
            workflow_event_recorder=self.build_workflow_event_recorder(),
        )

    def build_reminder_service(self) -> ReminderApplicationService:
        return ReminderApplicationService(
            unit_of_work_factory=self.build_reminder_unit_of_work_factory(),
            workflow_gateway=self.workflow_gateway,
            conversation_context_resolver=self.build_conversation_context_resolver(),
        )

    def build_reminder_unit_of_work_factory(self) -> ReminderUnitOfWorkFactory:
        def create_unit_of_work() -> SQLAlchemyReminderUnitOfWork:
            return SQLAlchemyReminderUnitOfWork(self.session_factory)

        return create_unit_of_work

    def build_model_invocation_recorder(self) -> MultiModelInvocationRecorder:
        return MultiModelInvocationRecorder(
            [
                DatabaseModelInvocationRecorder(
                    session_factory=self.session_factory,
                    enabled=self.settings.model_invocation_db_enabled,
                ),
                JsonlModelInvocationRecorder(
                    path=self.settings.model_invocation_jsonl_path,
                    enabled=self.settings.model_invocation_jsonl_enabled,
                ),
            ]
        )

    def build_message_event_recorder(self) -> MultiMessageEventRecorder:
        return MultiMessageEventRecorder(
            [
                DatabaseMessageEventRecorder(
                    session_factory=self.session_factory,
                    enabled=self.settings.message_event_db_enabled,
                ),
                JsonlMessageEventRecorder(
                    path=self.settings.message_event_jsonl_path,
                    enabled=self.settings.message_event_jsonl_enabled,
                ),
            ]
        )

    def build_conversation_context_resolver(self) -> ConversationContextResolver:
        return SqlAlchemyConversationContextResolver(self.session_factory)

    def build_tool_invocation_recorder(self) -> MultiToolInvocationRecorder:
        return MultiToolInvocationRecorder(
            [
                DatabaseToolInvocationRecorder(
                    session_factory=self.session_factory,
                    enabled=self.settings.tool_invocation_db_enabled,
                ),
                JsonlToolInvocationRecorder(
                    path=self.settings.tool_invocation_jsonl_path,
                    enabled=self.settings.tool_invocation_jsonl_enabled,
                ),
            ]
        )

    def build_messaging_adapter(self) -> MessagingAdapter:
        logging_adapter = LoggingMessagingAdapter()

        base_adapter: MessagingAdapter
        if self.settings.feishu_app_id and self.settings.feishu_app_secret:
            base_adapter = RoutingMessagingAdapter(
                default_adapter=logging_adapter,
                feishu_adapter=FeishuMessagingAdapter(settings=self.settings),
            )
        else:
            base_adapter = RoutingMessagingAdapter(default_adapter=logging_adapter)

        return RecordingMessagingAdapter(
            inner=base_adapter,
            recorder=self.build_message_event_recorder(),
        )

    def build_conversation_service(self) -> ConversationApplicationService:
        return ConversationApplicationService(
            conversation_context_resolver=self.build_conversation_context_resolver(),
            message_event_recorder=self.build_message_event_recorder(),
            handlers=self.build_conversation_handlers(),
        )

    def build_conversation_handlers(self) -> list[ConversationInboundHandler]:
        return [ReminderConversationHandler(self.build_reminder_service())]

    def build_audit_service(self) -> AuditQueryService:
        return AuditQueryService(self.session_factory)

    def build_workflow_event_recorder(self) -> MultiWorkflowEventRecorder:
        return MultiWorkflowEventRecorder(
            [
                DatabaseWorkflowEventRecorder(
                    session_factory=self.session_factory,
                    enabled=self.settings.workflow_event_db_enabled,
                ),
                JsonlWorkflowEventRecorder(
                    path=self.settings.workflow_event_jsonl_path,
                    enabled=self.settings.workflow_event_jsonl_enabled,
                ),
            ]
        )

    def build_feishu_webhook_handler(self) -> FeishuWebhookHandler:
        return FeishuWebhookHandler(
            settings=self.settings,
            inbound_event_recorder=ConversationInboundEventRecorder(
                self.build_conversation_service()
            ),
        )

    def build_feishu_long_connection_listener(self) -> FeishuLongConnectionListener:
        return FeishuLongConnectionListener(
            settings=self.settings,
            webhook_handler=FeishuWebhookHandler(
                settings=self.settings,
                inbound_event_recorder=ConversationInboundEventRecorder(
                    self.build_conversation_service()
                ),
                record_on_dispatch=True,
            ),
        )


@lru_cache
def get_container() -> ApplicationContainer:
    return ApplicationContainer(settings=get_settings())
