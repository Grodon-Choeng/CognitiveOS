from datetime import datetime
from uuid import UUID

from cashews import cache

from app.config import settings
from app.core.exceptions import NotFoundException
from app.core.repository import CursorPage
from app.enums import SortField, SortOrder
from app.models.knowledge_item import KnowledgeItem
from app.repositories.knowledge_item_repo import KnowledgeItemRepository
from app.utils.jsons import parse_json_field
from app.utils.logging import logger


class KnowledgeItemService:
    def __init__(self, repo: KnowledgeItemRepository) -> None:
        self._repo = repo

    async def get_id_by_uuid(self, uuid: UUID) -> int:
        cache_key = f"knowledge_item:uuid:{uuid}"
        cached_id = await cache.get(cache_key)

        if cached_id is not None:
            logger.debug(f"Cache hit for UUID->ID: {uuid}")
            return int(cached_id)

        item = await self._repo.get_by_uuid(uuid)
        if not item:
            raise NotFoundException("KnowledgeItem", uuid)

        await cache.set(cache_key, str(item.id), expire=settings.cache_default_ttl)
        logger.debug(f"Cache miss for UUID->ID: {uuid}, cached id={item.id}")
        return item.id

    async def get_by_uuid(self, uuid: UUID) -> KnowledgeItem:
        item_id = await self.get_id_by_uuid(uuid)
        return await self.get_by_id(item_id)

    async def get_by_id(self, item_id: int) -> KnowledgeItem:
        cache_key = f"knowledge_item:id:{item_id}"
        cached_data = await cache.get(cache_key)

        if cached_data is not None:
            logger.debug(f"Cache hit for ID->data: {item_id}")
            return self._deserialize_item(cached_data)

        item = await self._repo.get_by_id(item_id)
        if not item:
            raise NotFoundException("KnowledgeItem", item_id)

        await cache.set(cache_key, self._serialize_item(item), expire=settings.cache_default_ttl)
        logger.debug(f"Cache miss for ID->data: {item_id}")
        return item

    async def create(
        self, raw_text: str, source: str, tags: list[str] | None = None
    ) -> KnowledgeItem:
        if tags is None:
            tags = []
        item = await self._repo.create(raw_text=raw_text, source=source, tags=tags)
        logger.info(f"Created knowledge item: uuid={item.uuid}, source={source}")

        await self._cache_item(item)

        return item

    async def get_recent(self, limit: int = 10) -> list[KnowledgeItem]:
        return await self._repo.get_recent(limit=limit)

    async def cursor_paginate(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort_field: SortField = SortField.CREATED_AT,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> CursorPage[KnowledgeItem]:
        return await self._repo.cursor_paginate(
            limit=limit,
            cursor=cursor,
            sort_field=sort_field,
            sort_order=sort_order,
        )

    async def update_structured(
        self, uuid: UUID, structured_text: str, tags: list[str], links: list[str]
    ) -> bool:
        item_id = await self.get_id_by_uuid(uuid)
        result = await self._repo.update_structured(item_id, structured_text, tags, links)

        if result:
            await self._invalidate_cache(item_id, uuid)
            logger.info(f"Updated knowledge item: uuid={uuid}")

        return result

    async def update_embedding(self, item_id: int, embedding: list[float]) -> bool:
        result = await self._repo.update_by_id(item_id, embedding=embedding)
        if result:
            logger.info(f"Updated embedding for item: id={item_id}")
        return result is not None

    async def batch_update_embeddings(
        self, items: list[KnowledgeItem], embeddings: list[list[float]]
    ) -> int:
        count = 0
        for item, embedding in zip(items, embeddings, strict=False):
            await self._repo.update_by_id(item.id, embedding=embedding)
            count += 1
        logger.info(f"Updated embeddings for {count} items")
        return count

    async def search_by_tags(self, tags: list[str], limit: int = 10) -> list[KnowledgeItem]:
        return await self._repo.search_by_tags(tags, limit)

    async def filter_without_embedding(self, limit: int = 1000) -> list[KnowledgeItem]:
        items = await self._repo.filter(embedding=None)
        return items[:limit]

    @staticmethod
    def _serialize_item(item: KnowledgeItem) -> dict:
        return {
            "id": item.id,
            "uuid": str(item.uuid),
            "raw_text": item.raw_text,
            "structured_text": item.structured_text,
            "source": item.source,
            "tags": parse_json_field(item.tags),
            "links": parse_json_field(item.links),
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    @staticmethod
    def _deserialize_item(data: dict) -> KnowledgeItem:
        item = KnowledgeItem.__new__(KnowledgeItem)
        item.id = data["id"]
        item.uuid = UUID(data["uuid"])
        item.raw_text = data["raw_text"]
        item.structured_text = data["structured_text"]
        item.source = data["source"]
        item.tags = data["tags"]
        item.links = data["links"]
        item.created_at = datetime.fromisoformat(data["created_at"]) if data["created_at"] else None
        item.updated_at = datetime.fromisoformat(data["updated_at"]) if data["updated_at"] else None
        return item

    async def _cache_item(self, item: KnowledgeItem) -> None:
        uuid_cache_key = f"knowledge_item:uuid:{item.uuid}"
        id_cache_key = f"knowledge_item:id:{item.id}"

        await cache.set(uuid_cache_key, str(item.id), expire=settings.cache_default_ttl)
        await cache.set(id_cache_key, self._serialize_item(item), expire=settings.cache_default_ttl)

    @staticmethod
    async def _invalidate_cache(item_id: int, uuid: UUID) -> None:
        await cache.delete(f"knowledge_item:uuid:{uuid}")
        await cache.delete(f"knowledge_item:id:{item_id}")
        await cache.delete_match("knowledge_item:recent:*")
        logger.debug(f"Invalidated cache for item: id={item_id}, uuid={uuid}")
