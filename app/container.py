from dishka import Provider, Scope, provide

from app.bot.message_service import BotMessageService
from app.channels import IMManager
from app.config import settings
from app.note import NoteService
from app.repositories import (
    EmbeddingRecordRepository,
    KnowledgeItemRepository,
    MemoryRepository,
    PromptRepository,
    PromptTemplateRepository,
)
from app.services import (
    CaptureService,
    EmbeddingService,
    KnowledgeItemService,
    LLMService,
    MemoryEmbedder,
    MemoryFAISSStore,
    MemoryOrchestrator,
    MemoryRetriever,
    MemoryWriter,
    NotificationService,
    PromptService,
    PromptTemplateService,
    RetrievalService,
    StructuringService,
    VectorStore,
)
from app.services.cognitive_agent_service import CognitiveAgentService
from app.services.intent_graph_service import IntentGraphService


class AppProvider(Provider):
    @provide(scope=Scope.APP)
    def knowledge_item_repo(self) -> KnowledgeItemRepository:
        return KnowledgeItemRepository()

    @provide(scope=Scope.APP)
    def prompt_repo(self) -> PromptRepository:
        return PromptRepository()

    @provide(scope=Scope.APP)
    def memory_repo(self) -> MemoryRepository:
        return MemoryRepository()

    @provide(scope=Scope.APP)
    def embedding_record_repo(self) -> EmbeddingRecordRepository:
        return EmbeddingRecordRepository()

    @provide(scope=Scope.APP)
    def prompt_template_repo(self) -> PromptTemplateRepository:
        return PromptTemplateRepository()

    @provide(scope=Scope.APP)
    def knowledge_item_service(self, repo: KnowledgeItemRepository) -> KnowledgeItemService:
        return KnowledgeItemService(repo)

    @provide(scope=Scope.APP)
    def capture_service(self, knowledge_service: KnowledgeItemService) -> CaptureService:
        return CaptureService(knowledge_service)

    @provide(scope=Scope.APP)
    def structuring_service(self) -> StructuringService:
        return StructuringService(debug_mode=settings.markdown_debug_mode)

    @provide(scope=Scope.APP)
    def notification_service(self) -> NotificationService:
        if settings.im_enabled:
            configs = settings.get_im_configs()
            if configs:
                manager = IMManager(configs)
                return NotificationService(manager=manager)
        return NotificationService(manager=None)

    @provide(scope=Scope.APP)
    def llm_service(self) -> LLMService:
        return LLMService()

    @provide(scope=Scope.APP)
    def note_service(self) -> NoteService:
        return NoteService()

    @provide(scope=Scope.APP)
    def intent_graph_service(self, llm_service: LLMService) -> IntentGraphService:
        return IntentGraphService(llm_service=llm_service)

    @provide(scope=Scope.APP)
    def cognitive_agent_service(
        self,
        note_service: NoteService,
        llm_service: LLMService,
    ) -> CognitiveAgentService:
        return CognitiveAgentService(note_service=note_service, llm_service=llm_service)

    @provide(scope=Scope.APP)
    def bot_message_service(
        self,
        agent_service: CognitiveAgentService,
        llm_service: LLMService,
    ) -> BotMessageService:
        return BotMessageService(
            agent_service=agent_service,
            llm_service=llm_service,
        )

    @provide(scope=Scope.APP)
    def embedding_service(
        self, llm_service: LLMService, knowledge_service: KnowledgeItemService
    ) -> EmbeddingService:
        return EmbeddingService(llm_service, knowledge_service)

    @provide(scope=Scope.APP)
    def vector_store(self) -> VectorStore:
        return VectorStore()

    @provide(scope=Scope.APP)
    def memory_store(self) -> MemoryFAISSStore:
        return MemoryFAISSStore()

    @provide(scope=Scope.APP)
    def prompt_service(self, repo: PromptRepository) -> PromptService:
        return PromptService(repo)

    @provide(scope=Scope.APP)
    def prompt_template_service(self, repo: PromptTemplateRepository) -> PromptTemplateService:
        return PromptTemplateService(repo)

    @provide(scope=Scope.APP)
    def memory_embedder(self, llm_service: LLMService) -> MemoryEmbedder:
        return MemoryEmbedder(llm_service)

    @provide(scope=Scope.APP)
    def memory_retriever(
        self,
        store: MemoryFAISSStore,
        memory_repo: MemoryRepository,
    ) -> MemoryRetriever:
        return MemoryRetriever(store, memory_repo)

    @provide(scope=Scope.APP)
    def memory_writer(
        self,
        memory_repo: MemoryRepository,
        embedding_record_repo: EmbeddingRecordRepository,
        embedder: MemoryEmbedder,
        store: MemoryFAISSStore,
        llm_service: LLMService,
    ) -> MemoryWriter:
        return MemoryWriter(
            memory_repo=memory_repo,
            embedding_repo=embedding_record_repo,
            embedder=embedder,
            store=store,
            llm_service=llm_service,
        )

    @provide(scope=Scope.APP)
    def memory_orchestrator(
        self,
        embedder: MemoryEmbedder,
        retriever: MemoryRetriever,
        writer: MemoryWriter,
        prompt_template_service: PromptTemplateService,
    ) -> MemoryOrchestrator:
        return MemoryOrchestrator(embedder, retriever, writer, prompt_template_service)

    @provide(scope=Scope.APP)
    def retrieval_service(
        self,
        llm_service: LLMService,
        embedding_service: EmbeddingService,
        knowledge_service: KnowledgeItemService,
        vector_store: VectorStore,
        prompt_service: PromptService,
        memory_orchestrator: MemoryOrchestrator,
    ) -> RetrievalService:
        return RetrievalService(
            llm_service,
            embedding_service,
            knowledge_service,
            vector_store,
            prompt_service,
            memory_orchestrator,
        )
