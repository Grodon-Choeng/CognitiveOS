from dishka import AsyncContainer, Provider, Scope, from_context, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.audit.service import AuditQueryService
from app.application.conversations.intent_handler import (
    IntentConversationHandler,
    LLMFirstConversationIntentClassifier,
)
from app.application.conversations.service import (
    ConversationApplicationService,
    LLMConversationFallbackResponder,
)
from app.application.memory.ports import MemoryUnitOfWorkFactory
from app.application.memory.service import MemoryApplicationService
from app.application.overview.service import OverviewApplicationService
from app.application.reminders.conversation_handler import ReminderConversationHandler
from app.application.reminders.ports import ReminderUnitOfWorkFactory
from app.application.reminders.service import ReminderApplicationService
from app.application.tasks.ports import TaskUnitOfWorkFactory
from app.application.tasks.service import TaskApplicationService
from app.bootstrap.inbound_events import ConversationInboundEventRecorder
from app.config.settings import Settings
from app.infrastructure.conversations import SqlAlchemyConversationContextResolver
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.db.uow import (
    SQLAlchemyMemoryUnitOfWork,
    SQLAlchemyReminderUnitOfWork,
    SQLAlchemyTaskUnitOfWork,
)
from app.infrastructure.integrations.messaging import (
    FeishuLongConnectionListener,
    FeishuMessagingAdapter,
    FeishuWebhookHandler,
    LoggingMessagingAdapter,
    MessagingAdapter,
    RecordingMessagingAdapter,
    RoutingMessagingAdapter,
)
from app.infrastructure.llm.gateway import RecordingLLMGateway
from app.infrastructure.llm.local_gateway import LocalChatLLMGateway
from app.infrastructure.llm.openai_gateway import OpenAIChatLLMGateway
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
    build_api_key_suffix,
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

AsyncSessionFactory = async_sessionmaker[AsyncSession]


class ContextProvider(Provider):
    settings = from_context(Settings, scope=Scope.APP)


class ApplicationProvider(Provider):
    @staticmethod
    def _build_conversation_llm_gateway(
        *,
        settings: Settings,
        model_invocation_recorder: MultiModelInvocationRecorder,
    ) -> RecordingLLMGateway | None:
        if not settings.conversation_intent_model:
            return None
        provider = settings.conversation_llm_provider.strip().casefold()
        if provider == "openai":
            if not settings.openai_api_key:
                return None
            return RecordingLLMGateway(
                OpenAIChatLLMGateway(
                    api_key=settings.openai_api_key,
                    model=settings.conversation_intent_model,
                    base_url=settings.openai_base_url,
                    timeout_seconds=settings.conversation_intent_llm_timeout_seconds,
                ),
                model_invocation_recorder,
            )
        if provider == "local":
            return RecordingLLMGateway(
                LocalChatLLMGateway(
                    model=settings.conversation_intent_model,
                    base_url=settings.local_llm_base_url,
                    timeout_seconds=settings.conversation_intent_llm_timeout_seconds,
                ),
                model_invocation_recorder,
            )
        raise ValueError(
            f"不支持的 conversation llm provider：{settings.conversation_llm_provider}"
        )

    @provide(scope=Scope.APP)
    def provide_session_factory(self, settings: Settings) -> AsyncSessionFactory:
        return get_session_factory(settings)

    @provide(scope=Scope.APP)
    def provide_reminder_uow_factory(
        self,
        session_factory: AsyncSessionFactory,
    ) -> ReminderUnitOfWorkFactory:
        return _build_reminder_uow_factory(session_factory)

    @provide(scope=Scope.APP)
    def provide_memory_uow_factory(
        self,
        session_factory: AsyncSessionFactory,
    ) -> MemoryUnitOfWorkFactory:
        return _build_memory_uow_factory(session_factory)

    @provide(scope=Scope.APP)
    def provide_task_uow_factory(
        self,
        session_factory: AsyncSessionFactory,
    ) -> TaskUnitOfWorkFactory:
        return _build_task_uow_factory(session_factory)

    @provide(scope=Scope.APP)
    def provide_model_invocation_recorder(
        self,
        settings: Settings,
        session_factory: AsyncSessionFactory,
    ) -> MultiModelInvocationRecorder:
        return MultiModelInvocationRecorder(
            [
                DatabaseModelInvocationRecorder(
                    session_factory=session_factory,
                    enabled=settings.model_invocation_db_enabled,
                ),
                JsonlModelInvocationRecorder(
                    path=settings.model_invocation_jsonl_path,
                    enabled=settings.model_invocation_jsonl_enabled,
                ),
            ]
        )

    @provide(scope=Scope.APP)
    def provide_message_event_recorder(
        self,
        settings: Settings,
        session_factory: AsyncSessionFactory,
    ) -> MultiMessageEventRecorder:
        return MultiMessageEventRecorder(
            [
                DatabaseMessageEventRecorder(
                    session_factory=session_factory,
                    enabled=settings.message_event_db_enabled,
                ),
                JsonlMessageEventRecorder(
                    path=settings.message_event_jsonl_path,
                    enabled=settings.message_event_jsonl_enabled,
                ),
            ]
        )

    @provide(scope=Scope.APP)
    def provide_tool_invocation_recorder(
        self,
        settings: Settings,
        session_factory: AsyncSessionFactory,
    ) -> MultiToolInvocationRecorder:
        return MultiToolInvocationRecorder(
            [
                DatabaseToolInvocationRecorder(
                    session_factory=session_factory,
                    enabled=settings.tool_invocation_db_enabled,
                ),
                JsonlToolInvocationRecorder(
                    path=settings.tool_invocation_jsonl_path,
                    enabled=settings.tool_invocation_jsonl_enabled,
                ),
            ]
        )

    @provide(scope=Scope.APP)
    def provide_workflow_event_recorder(
        self,
        settings: Settings,
        session_factory: AsyncSessionFactory,
    ) -> MultiWorkflowEventRecorder:
        return MultiWorkflowEventRecorder(
            [
                DatabaseWorkflowEventRecorder(
                    session_factory=session_factory,
                    enabled=settings.workflow_event_db_enabled,
                ),
                JsonlWorkflowEventRecorder(
                    path=settings.workflow_event_jsonl_path,
                    enabled=settings.workflow_event_jsonl_enabled,
                ),
            ]
        )

    @provide(scope=Scope.APP)
    def provide_conversation_context_resolver(
        self,
        session_factory: AsyncSessionFactory,
    ) -> SqlAlchemyConversationContextResolver:
        return SqlAlchemyConversationContextResolver(session_factory)

    @provide(scope=Scope.APP)
    def provide_workflow_gateway(
        self,
        settings: Settings,
        workflow_event_recorder: MultiWorkflowEventRecorder,
    ) -> TemporalReminderWorkflowGateway:
        return TemporalReminderWorkflowGateway(
            settings=settings,
            workflow_event_recorder=workflow_event_recorder,
        )

    @provide(scope=Scope.APP)
    def provide_reminder_service(
        self,
        reminder_uow_factory: ReminderUnitOfWorkFactory,
        workflow_gateway: TemporalReminderWorkflowGateway,
        conversation_context_resolver: SqlAlchemyConversationContextResolver,
    ) -> ReminderApplicationService:
        return ReminderApplicationService(
            unit_of_work_factory=reminder_uow_factory,
            workflow_gateway=workflow_gateway,
            conversation_context_resolver=conversation_context_resolver,
        )

    @provide(scope=Scope.APP)
    def provide_memory_service(
        self,
        memory_uow_factory: MemoryUnitOfWorkFactory,
        conversation_context_resolver: SqlAlchemyConversationContextResolver,
    ) -> MemoryApplicationService:
        return MemoryApplicationService(
            unit_of_work_factory=memory_uow_factory,
            conversation_context_resolver=conversation_context_resolver,
        )

    @provide(scope=Scope.APP)
    def provide_task_service(
        self,
        task_uow_factory: TaskUnitOfWorkFactory,
        conversation_context_resolver: SqlAlchemyConversationContextResolver,
    ) -> TaskApplicationService:
        return TaskApplicationService(
            unit_of_work_factory=task_uow_factory,
            conversation_context_resolver=conversation_context_resolver,
        )

    @provide(scope=Scope.APP)
    def provide_audit_service(
        self,
        session_factory: AsyncSessionFactory,
    ) -> AuditQueryService:
        return AuditQueryService(session_factory)

    @provide(scope=Scope.APP)
    def provide_overview_service(
        self,
        reminder_service: ReminderApplicationService,
        task_service: TaskApplicationService,
        memory_service: MemoryApplicationService,
        audit_service: AuditQueryService,
    ) -> OverviewApplicationService:
        return OverviewApplicationService(
            reminder_service=reminder_service,
            task_service=task_service,
            memory_service=memory_service,
            audit_service=audit_service,
        )

    @provide(scope=Scope.APP)
    def provide_conversation_intent_classifier(
        self,
        settings: Settings,
        model_invocation_recorder: MultiModelInvocationRecorder,
    ) -> LLMFirstConversationIntentClassifier:
        llm_gateway = self._build_conversation_llm_gateway(
            settings=settings,
            model_invocation_recorder=model_invocation_recorder,
        )
        return LLMFirstConversationIntentClassifier(
            llm_gateway=llm_gateway,
            model=settings.conversation_intent_model,
            api_key_suffix=build_api_key_suffix(settings.openai_api_key),
            provider=settings.conversation_llm_provider,
        )

    @provide(scope=Scope.APP)
    def provide_conversation_service(
        self,
        conversation_context_resolver: SqlAlchemyConversationContextResolver,
        message_event_recorder: MultiMessageEventRecorder,
        audit_service: AuditQueryService,
        reminder_service: ReminderApplicationService,
        conversation_intent_classifier: LLMFirstConversationIntentClassifier,
        task_service: TaskApplicationService,
        memory_service: MemoryApplicationService,
        overview_service: OverviewApplicationService,
        settings: Settings,
        model_invocation_recorder: MultiModelInvocationRecorder,
    ) -> ConversationApplicationService:
        llm_gateway = self._build_conversation_llm_gateway(
            settings=settings,
            model_invocation_recorder=model_invocation_recorder,
        )
        return ConversationApplicationService(
            conversation_context_resolver=conversation_context_resolver,
            message_event_recorder=message_event_recorder,
            handlers=[
                ReminderConversationHandler(reminder_service),
                IntentConversationHandler(
                    classifier=conversation_intent_classifier,
                    task_service=task_service,
                    memory_service=memory_service,
                    reminder_service=reminder_service,
                    overview_service=overview_service,
                ),
            ],
            fallback_responder=LLMConversationFallbackResponder(
                llm_gateway=llm_gateway,
                model=settings.conversation_intent_model,
                api_key_suffix=build_api_key_suffix(settings.openai_api_key),
                history_reader=audit_service,
                provider=settings.conversation_llm_provider,
            ),
        )

    @provide(scope=Scope.APP)
    def provide_messaging_adapter(
        self,
        settings: Settings,
        message_event_recorder: MultiMessageEventRecorder,
    ) -> MessagingAdapter:
        logging_adapter = LoggingMessagingAdapter()
        base_adapter: MessagingAdapter
        if settings.feishu_app_id and settings.feishu_app_secret:
            base_adapter = RoutingMessagingAdapter(
                default_adapter=logging_adapter,
                feishu_adapter=FeishuMessagingAdapter(settings=settings),
            )
        else:
            base_adapter = RoutingMessagingAdapter(default_adapter=logging_adapter)

        return RecordingMessagingAdapter(
            inner=base_adapter,
            recorder=message_event_recorder,
        )

    @provide(scope=Scope.APP)
    def provide_inbound_event_recorder(
        self,
        conversation_service: ConversationApplicationService,
        messaging_adapter: MessagingAdapter,
    ) -> ConversationInboundEventRecorder:
        return ConversationInboundEventRecorder(
            conversation_service=conversation_service,
            messaging_adapter=messaging_adapter,
        )

    @provide(scope=Scope.APP)
    def provide_feishu_webhook_handler(
        self,
        settings: Settings,
        inbound_event_recorder: ConversationInboundEventRecorder,
    ) -> FeishuWebhookHandler:
        return FeishuWebhookHandler(
            settings=settings,
            inbound_event_recorder=inbound_event_recorder,
        )

    @provide(scope=Scope.APP)
    def provide_feishu_long_connection_listener(
        self,
        settings: Settings,
        inbound_event_recorder: ConversationInboundEventRecorder,
    ) -> FeishuLongConnectionListener:
        return FeishuLongConnectionListener(
            settings=settings,
            webhook_handler=FeishuWebhookHandler(
                settings=settings,
                inbound_event_recorder=inbound_event_recorder,
                record_on_dispatch=True,
            ),
        )


def create_runtime_container(settings: Settings) -> AsyncContainer:
    return make_async_container(
        ContextProvider(),
        ApplicationProvider(),
        context={Settings: settings},
    )


def create_http_container(settings: Settings) -> AsyncContainer:
    return make_async_container(
        ContextProvider(),
        ApplicationProvider(),
        FastapiProvider(),
        context={Settings: settings},
    )


def _build_reminder_uow_factory(
    session_factory: AsyncSessionFactory,
) -> ReminderUnitOfWorkFactory:
    def create_unit_of_work() -> SQLAlchemyReminderUnitOfWork:
        return SQLAlchemyReminderUnitOfWork(session_factory)

    return create_unit_of_work


def _build_memory_uow_factory(
    session_factory: AsyncSessionFactory,
) -> MemoryUnitOfWorkFactory:
    def create_unit_of_work() -> SQLAlchemyMemoryUnitOfWork:
        return SQLAlchemyMemoryUnitOfWork(session_factory)

    return create_unit_of_work


def _build_task_uow_factory(
    session_factory: AsyncSessionFactory,
) -> TaskUnitOfWorkFactory:
    def create_unit_of_work() -> SQLAlchemyTaskUnitOfWork:
        return SQLAlchemyTaskUnitOfWork(session_factory)

    return create_unit_of_work
