from dishka import Provider, Scope, provide

from app.config import settings
from app.im import create_adapter
from app.repositories.knowledge_item_repo import KnowledgeItemRepository
from app.repositories.prompt_repo import PromptRepository
from app.services.capture_service import CaptureService
from app.services.embedding_service import EmbeddingService
from app.services.knowledge_item_service import KnowledgeItemService
from app.services.llm_service import LLMService
from app.services.notification_service import NotificationService
from app.services.prompt_service import PromptService
from app.services.retrieval_service import RetrievalService
from app.services.structuring_service import StructuringService
from app.services.vector_store import VectorStore


class AppProvider(Provider):
    @provide(scope=Scope.APP)
    def knowledge_item_repo(self) -> KnowledgeItemRepository:
        return KnowledgeItemRepository()

    @provide(scope=Scope.APP)
    def prompt_repo(self) -> PromptRepository:
        return PromptRepository()

    @provide(scope=Scope.APP)
    def knowledge_item_service(
        self, repo: KnowledgeItemRepository
    ) -> KnowledgeItemService:
        return KnowledgeItemService(repo)

    @provide(scope=Scope.APP)
    def capture_service(
        self, knowledge_service: KnowledgeItemService
    ) -> CaptureService:
        return CaptureService(knowledge_service)

    @provide(scope=Scope.APP)
    def structuring_service(self) -> StructuringService:
        return StructuringService(debug_mode=settings.markdown_debug_mode)

    @provide(scope=Scope.APP)
    def notification_service(self) -> NotificationService:
        if settings.im_enabled and settings.im_webhook_url:
            adapter = create_adapter(
                provider=settings.im_provider,
                webhook_url=settings.im_webhook_url,
                secret=settings.im_secret,
            )
            return NotificationService(adapter=adapter)
        return NotificationService(adapter=None)

    @provide(scope=Scope.APP)
    def llm_service(self) -> LLMService:
        return LLMService()

    @provide(scope=Scope.APP)
    def embedding_service(
        self, llm_service: LLMService, repo: KnowledgeItemRepository
    ) -> EmbeddingService:
        return EmbeddingService(llm_service, repo)

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
