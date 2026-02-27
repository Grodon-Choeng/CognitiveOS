import json

from app.core import BaseRepository
from app.models import KnowledgeItem


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
        all_items = await self.list(limit=1000)

        matched = []
        for item in all_items:
            item_tags = item.tags if isinstance(item.tags, list) else json.loads(item.tags or "[]")
            if any(tag in item_tags for tag in tags):
                matched.append(item)
                if len(matched) >= limit:
                    break

        return matched
