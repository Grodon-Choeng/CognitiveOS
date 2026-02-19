from dishka import Provider, Scope, provide

from app.repositories.knowledge_item_repo import KnowledgeItemRepository
from app.services.capture_service import CaptureService
from app.services.knowledge_item_service import KnowledgeItemService
from app.services.structuring_service import StructuringService

from app.config import settings


class AppProvider(Provider):
    @provide(scope=Scope.APP)
    def knowledge_item_repo(self) -> KnowledgeItemRepository:
        return KnowledgeItemRepository()

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
