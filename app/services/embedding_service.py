from typing import TYPE_CHECKING

from app.services.llm_service import LLMService
from app.utils.logging import logger

if TYPE_CHECKING:
    from app.models.knowledge_item import KnowledgeItem
    from app.repositories.knowledge_item_repo import KnowledgeItemRepository


class EmbeddingService:
    def __init__(
        self, llm_service: LLMService, repo: "KnowledgeItemRepository"
    ) -> None:
        self.llm_service = llm_service
        self.repo = repo

    async def generate_embedding(self, item: "KnowledgeItem") -> list[float]:
        text = self._prepare_text(item)
        embedding = await self.llm_service.get_embedding(text)
        return embedding

    async def generate_and_store(self, item: "KnowledgeItem") -> list[float]:
        embedding = await self.generate_embedding(item)

        await self.repo.update_by_id(item.id, embedding=embedding)
        logger.info(f"Stored embedding for item {item.id}")

        return embedding

    async def batch_generate(self, items: list["KnowledgeItem"]) -> list[list[float]]:
        texts = [self._prepare_text(item) for item in items]
        embeddings = await self.llm_service.get_embeddings(texts)
        return embeddings

    async def batch_generate_and_store(
        self, items: list["KnowledgeItem"]
    ) -> list[list[float]]:
        embeddings = await self.batch_generate(items)

        for item, embedding in zip(items, embeddings):
            await self.repo.update_by_id(item.id, embedding=embedding)

        logger.info(f"Stored embeddings for {len(items)} items")
        return embeddings

    @staticmethod
    def _prepare_text(item: "KnowledgeItem") -> str:
        parts = []

        if item.structured_text:
            parts.append(item.structured_text)
        else:
            parts.append(item.raw_text)

        if item.tags:
            tags_str = " ".join(f"#{tag}" for tag in item.tags)
            parts.append(f"Tags: {tags_str}")

        return "\n\n".join(parts)
