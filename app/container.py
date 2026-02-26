from dishka import Provider, Scope, provide

from app.channels import IMManager
from app.config import settings
from app.repositories import KnowledgeItemRepository, PromptRepository
from app.services import (
    CaptureService,
    EmbeddingService,
    KnowledgeItemService,
    LLMService,
    NotificationService,
    PromptService,
    RetrievalService,
    StructuringService,
    VectorStore,
)


class AppProvider(Provider):
    @provide(scope=Scope.APP)
    def knowledge_item_repo(self) -> KnowledgeItemRepository:
        return KnowledgeItemRepository()

    @provide(scope=Scope.APP)
    def prompt_repo(self) -> PromptRepository:
        return PromptRepository()

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
    def embedding_service(
        self, llm_service: LLMService, knowledge_service: KnowledgeItemService
    ) -> EmbeddingService:
        return EmbeddingService(llm_service, knowledge_service)

    @provide(scope=Scope.APP)
    def vector_store(self) -> VectorStore:
        return VectorStore()

    @provide(scope=Scope.APP)
    def prompt_service(self, repo: PromptRepository) -> PromptService:
        return PromptService(repo)

    @provide(scope=Scope.APP)
    def retrieval_service(
        self,
        llm_service: LLMService,
        embedding_service: EmbeddingService,
        knowledge_service: KnowledgeItemService,
        vector_store: VectorStore,
        prompt_service: PromptService,
    ) -> RetrievalService:
        return RetrievalService(
            llm_service,
            embedding_service,
            knowledge_service,
            vector_store,
            prompt_service,
        )
