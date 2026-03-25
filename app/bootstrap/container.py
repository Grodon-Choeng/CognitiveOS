from dishka import AsyncContainer, Provider, Scope, from_context, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.audit.service import AuditQueryService
from app.application.conversations.inbound_processor import ConversationInboundProcessor
from app.application.conversations.intent_handler import (
    LegacyIntentConversationHandler,
    LLMFirstConversationIntentClassifier,
)
from app.application.conversations.kernel.executor import AssistantExecutor
from app.application.conversations.kernel.facade import ConversationKernelFacade
from app.application.conversations.kernel.planner import AssistantActionPlanner
from app.application.conversations.kernel.renderer import AssistantResponseRenderer
from app.application.conversations.kernel.resolver import ReferenceResolver
from app.application.conversations.kernel.state import AssistantTurnContextBuilder
from app.application.conversations.ports import AssistantTurnStateStore
from app.application.conversations.service import (
    ConversationApplicationService,
    LLMConversationFallbackResponder,
)
from app.application.debug_im.ports import DebugIMMessageStore
from app.application.debug_im.service import DebugIMApplicationService
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
from app.infrastructure.conversations.turn_state_store import SQLAlchemyAssistantTurnStateStore
from app.infrastructure.db.session import get_session_factory
from app.infrastructure.db.uow import (
    SQLAlchemyMemoryUnitOfWork,
    SQLAlchemyReminderUnitOfWork,
    SQLAlchemyTaskUnitOfWork,
)
from app.infrastructure.debug_im import SQLAlchemyDebugIMMessageStore
from app.infrastructure.integrations.messaging import (
    DebugIMMessagingAdapter,
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
        model = settings.effective_conversation_intent_model
        if model is None:
            return None
        provider = settings.effective_conversation_llm_provider
        endpoint = settings.effective_conversation_llm_endpoint
        api_key = settings.effective_conversation_llm_api_key
        if provider == "openai":
            if api_key is None:
                return None
            return RecordingLLMGateway(
                OpenAIChatLLMGateway(
                    api_key=api_key,
                    model=model,
                    base_url=endpoint,
                    timeout_seconds=settings.conversation_intent_llm_timeout_seconds,
                ),
                model_invocation_recorder,
            )
        if provider == "local":
            return RecordingLLMGateway(
                LocalChatLLMGateway(
                    model=model,
                    base_url=endpoint,
                    timeout_seconds=settings.conversation_intent_llm_timeout_seconds,
                ),
                model_invocation_recorder,
            )
        raise ValueError(f"不支持的 conversation llm provider：{provider}")

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
    def provide_debug_im_message_store(
        self,
        session_factory: AsyncSessionFactory,
    ) -> DebugIMMessageStore:
        return SQLAlchemyDebugIMMessageStore(session_factory)

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
            model=settings.effective_conversation_intent_model,
            api_key_suffix=build_api_key_suffix(settings.effective_conversation_llm_api_key),
            provider=settings.effective_conversation_llm_provider,
        )

    @provide(scope=Scope.APP)
    def provide_reference_resolver(self) -> ReferenceResolver:
        return ReferenceResolver()

    @provide(scope=Scope.APP)
    def provide_assistant_turn_state_store(
        self,
        session_factory: AsyncSessionFactory,
    ) -> AssistantTurnStateStore:
        return SQLAlchemyAssistantTurnStateStore(session_factory)

    @provide(scope=Scope.APP)
    def provide_turn_context_builder(
        self,
        overview_service: OverviewApplicationService,
        audit_service: AuditQueryService,
        reminder_service: ReminderApplicationService,
        assistant_turn_state_store: AssistantTurnStateStore,
    ) -> AssistantTurnContextBuilder:
        return AssistantTurnContextBuilder(
            overview_service=overview_service,
            history_reader=audit_service,
            reminder_reader=reminder_service,
            turn_state_store=assistant_turn_state_store,
        )

    @provide(scope=Scope.APP)
    def provide_assistant_action_planner(
        self,
        conversation_intent_classifier: LLMFirstConversationIntentClassifier,
    ) -> AssistantActionPlanner:
        return AssistantActionPlanner(classifier=conversation_intent_classifier)

    @provide(scope=Scope.APP)
    def provide_assistant_executor(
        self,
        task_service: TaskApplicationService,
        reminder_service: ReminderApplicationService,
        memory_service: MemoryApplicationService,
        overview_service: OverviewApplicationService,
        reference_resolver: ReferenceResolver,
    ) -> AssistantExecutor:
        return AssistantExecutor(
            task_service=task_service,
            reminder_service=reminder_service,
            memory_service=memory_service,
            overview_service=overview_service,
            resolver=reference_resolver,
        )

    @provide(scope=Scope.APP)
    def provide_assistant_response_renderer(self) -> AssistantResponseRenderer:
        return AssistantResponseRenderer()

    @provide(scope=Scope.APP)
    def provide_conversation_kernel_facade(
        self,
        turn_context_builder: AssistantTurnContextBuilder,
        assistant_action_planner: AssistantActionPlanner,
        assistant_executor: AssistantExecutor,
        assistant_response_renderer: AssistantResponseRenderer,
    ) -> ConversationKernelFacade:
        return ConversationKernelFacade(
            turn_context_builder=turn_context_builder,
            planner=assistant_action_planner,
            executor=assistant_executor,
            renderer=assistant_response_renderer,
        )

    @provide(scope=Scope.APP)
    def provide_legacy_intent_handler(
        self,
        conversation_kernel_facade: ConversationKernelFacade,
    ) -> LegacyIntentConversationHandler:
        return LegacyIntentConversationHandler(kernel_facade=conversation_kernel_facade)

    @provide(scope=Scope.APP)
    def provide_conversation_service(
        self,
        conversation_context_resolver: SqlAlchemyConversationContextResolver,
        message_event_recorder: MultiMessageEventRecorder,
        audit_service: AuditQueryService,
        reminder_service: ReminderApplicationService,
        conversation_kernel_facade: ConversationKernelFacade,
        assistant_turn_state_store: AssistantTurnStateStore,
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
            reminder_handler=ReminderConversationHandler(reminder_service),
            kernel_facade=conversation_kernel_facade,
            turn_state_store=assistant_turn_state_store,
            fallback_responder=LLMConversationFallbackResponder(
                llm_gateway=llm_gateway,
                model=settings.effective_conversation_intent_model,
                api_key_suffix=build_api_key_suffix(settings.effective_conversation_llm_api_key),
                history_reader=audit_service,
                provider=settings.effective_conversation_llm_provider,
            ),
        )

    @provide(scope=Scope.APP)
    def provide_conversation_inbound_processor(
        self,
        conversation_service: ConversationApplicationService,
        messaging_adapter: MessagingAdapter,
    ) -> ConversationInboundProcessor:
        return ConversationInboundProcessor(
            conversation_service=conversation_service,
            messaging_adapter=messaging_adapter,
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
                debug_im_adapter=DebugIMMessagingAdapter(),
                feishu_adapter=FeishuMessagingAdapter(settings=settings),
            )
        else:
            base_adapter = RoutingMessagingAdapter(
                default_adapter=logging_adapter,
                debug_im_adapter=DebugIMMessagingAdapter(),
            )

        return RecordingMessagingAdapter(
            inner=base_adapter,
            recorder=message_event_recorder,
        )

    @provide(scope=Scope.APP)
    def provide_inbound_event_recorder(
        self,
        inbound_processor: ConversationInboundProcessor,
    ) -> ConversationInboundEventRecorder:
        return ConversationInboundEventRecorder(
            inbound_processor=inbound_processor,
        )

    @provide(scope=Scope.APP)
    def provide_debug_im_service(
        self,
        inbound_processor: ConversationInboundProcessor,
        debug_im_message_store: DebugIMMessageStore,
    ) -> DebugIMApplicationService:
        return DebugIMApplicationService(
            inbound_processor=inbound_processor,
            message_store=debug_im_message_store,
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
