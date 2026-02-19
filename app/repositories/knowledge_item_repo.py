from app.core.repository import BaseRepository
from app.models.knowledge_item import KnowledgeItem


class KnowledgeItemRepository(BaseRepository[KnowledgeItem]):
    def __init__(self) -> None:
        super().__init__(KnowledgeItem)

    async def get_recent(self, limit: int = 10) -> list[KnowledgeItem]:
        return await self.list(limit=limit, order_by=self.get_col("created_at"))

    async def update_structured(
        self, item_id: int, structured_text: str, tags: list[str], links: list[str]
    ) -> bool:
        result = await self.update_by_id(
            item_id, structured_text=structured_text, tags=tags, links=links
        )
        return result is not None

    async def search_by_tags(self, tags: list[str], limit: int = 10) -> list[KnowledgeItem]:
        query = self.model.objects()
        for tag in tags:
            query = query.where(self.get_col("tags").contains(tag))
        return await query.limit(limit).run()
