from uuid import UUID

from cashews import cache

from app.config import settings
from app.core.exceptions import NotFoundError
from app.core.repository import CursorPage
from app.core.service import BaseService
from app.enums import SortField, SortOrder
from app.models.knowledge_item import KnowledgeItem
from app.repositories.knowledge_item_repo import KnowledgeItemRepository
from app.utils.logging import logger


class KnowledgeItemService(BaseService[KnowledgeItem, KnowledgeItemRepository]):
    cache_prefix = "knowledge_item"
    cache_ttl = settings.cache_default_ttl

    def __init__(self, repo: KnowledgeItemRepository) -> None:
        super().__init__(repo)

    def _cache_key_uuid_to_id(self, uuid: UUID) -> str:
        return self._cache_key("uuid2id", uuid)

    async def get_by_id(self, item_id: int) -> KnowledgeItem:
        key = self._cache_key_by_id(item_id)
        cached = await self._get_cached(KnowledgeItem, key)
        if cached is not None:
            return cached

        item = await self._repo.get_by_id(item_id)
        if not item:
            raise NotFoundError("KnowledgeItem", item_id)

        await self._set_cached(item, key)
        await cache.set(self._cache_key_uuid_to_id(item.uuid), item.id, expire=self.cache_ttl)
        return item

    async def get_by_uuid(self, uuid: UUID) -> KnowledgeItem:
        uuid2id_key = self._cache_key_uuid_to_id(uuid)
        item_id = await cache.get(uuid2id_key)

        if item_id is not None:
            return await self.get_by_id(item_id)

        item = await self._repo.get_by_uuid(uuid)
        if not item:
            raise NotFoundError("KnowledgeItem", uuid)

        await self._set_cached(item, self._cache_key_by_id(item.id))
        await cache.set(uuid2id_key, item.id, expire=self.cache_ttl)
        return item

    async def get_by_ids(self, item_ids: list[int]) -> list[KnowledgeItem]:
        if not item_ids:
            return []

        keys = [self._cache_key_by_id(item_id) for item_id in item_ids]
        cached_items = await self._get_cached_batch(KnowledgeItem, keys)

        missing_ids = []
        for i, (item_id, cached) in enumerate(zip(item_ids, cached_items, strict=False)):
            if cached is None:
                missing_ids.append((i, item_id))

        for i, item_id in missing_ids:
            try:
                item = await self._repo.get_by_id(item_id)
                if item:
                    await self._set_cached(item, self._cache_key_by_id(item_id))
                    cached_items[i] = item
            except Exception as e:
                logger.error(f"Failed to load item {item_id}: {e}")

        return [item for item in cached_items if item is not None]

    async def create(
        self, raw_text: str, source: str, tags: list[str] | None = None
    ) -> KnowledgeItem:
        if tags is None:
            tags = []
        item = await self._repo.create(raw_text=raw_text, source=source, tags=tags)
        logger.info(f"Created knowledge item: uuid={item.uuid}, source={source}")

        await self._cache_item(item)
        await cache.set(self._cache_key_uuid_to_id(item.uuid), item.id, expire=self.cache_ttl)
        await self._invalidate_list_cache()

        return item

    async def get_recent(self, limit: int = 10) -> list[KnowledgeItem]:
        items = await self._repo.get_recent(limit=limit)
        for item in items:
            await self._set_cached(item, self._cache_key_by_id(item.id))
        return items

    async def cursor_paginate(
        self,
        limit: int = 20,
        cursor: str | None = None,
        sort_field: SortField = SortField.CREATED_AT,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> CursorPage[KnowledgeItem]:
        list_key = self._cache_key_list(
            sort_field.value, sort_order.value, limit, cursor or "first"
        )

        cached_data = await cache.get(list_key)
        if cached_data is not None:
            logger.debug(f"Cache hit for list: {list_key}")
            if isinstance(cached_data, dict):
                item_ids = cached_data.get("item_ids", [])
                has_more = cached_data.get("has_more", False)
                next_cursor = cached_data.get("next_cursor")
            elif isinstance(cached_data, list):
                await cache.delete(list_key)
                logger.debug(f"Cache format outdated, deleted: {list_key}")
                page = await self._repo.cursor_paginate(
                    limit=limit,
                    cursor=cursor,
                    sort_field=sort_field,
                    sort_order=sort_order,
                )
                cache_data = {
                    "item_ids": [item.id for item in page.items],
                    "has_more": page.has_more,
                    "next_cursor": page.next_cursor,
                }
                await cache.set(list_key, cache_data, expire=self.cache_ttl)
                for item in page.items:
                    await self._set_cached(item, self._cache_key_by_id(item.id))
                return page
            else:
                item_ids = []
                has_more = False
                next_cursor = None
            items = await self.get_by_ids(item_ids[:limit])
            return CursorPage(
                items=items,
                next_cursor=next_cursor,
                has_more=has_more,
            )

        page = await self._repo.cursor_paginate(
            limit=limit,
            cursor=cursor,
            sort_field=sort_field,
            sort_order=sort_order,
        )

        cache_data = {
            "item_ids": [item.id for item in page.items],
            "has_more": page.has_more,
            "next_cursor": page.next_cursor,
        }
        await cache.set(list_key, cache_data, expire=self.cache_ttl)

        for item in page.items:
            await self._set_cached(item, self._cache_key_by_id(item.id))

        logger.debug(f"Cache miss for list: {list_key}")
        return page

    async def update_structured(
        self, uuid: UUID, structured_text: str, tags: list[str], links: list[str]
    ) -> bool:
        item = await self.get_by_uuid(uuid)
        result = await self._repo.update_structured(item.id, structured_text, tags, links)

        if result:
            await self._delete_cached(
                self._cache_key_by_id(item.id),
                self._cache_key_uuid_to_id(uuid),
            )
            logger.info(f"Updated knowledge item: uuid={uuid}")

        return result

    async def update_embedding(self, item_id: int, embedding: list[float]) -> bool:
        result = await self._repo.update_by_id(item_id, embedding=embedding)
        if result:
            await self._delete_cached(self._cache_key_by_id(item_id))
            logger.info(f"Updated embedding for item: id={item_id}")
        return result is not None

    async def batch_update_embeddings(
        self, items: list[KnowledgeItem], embeddings: list[list[float]]
    ) -> int:
        count = 0
        for item, embedding in zip(items, embeddings, strict=False):
            await self._repo.update_by_id(item.id, embedding=embedding)
            await self._delete_cached(self._cache_key_by_id(item.id))
            count += 1
        logger.info(f"Updated embeddings for {count} items")
        return count

    async def search_by_tags(self, tags: list[str], limit: int = 10) -> list[KnowledgeItem]:
        items = await self._repo.search_by_tags(tags, limit)
        for item in items:
            await self._set_cached(item, self._cache_key_by_id(item.id))
        return items

    async def filter_without_embedding(self, limit: int = 1000) -> list[KnowledgeItem]:
        items = await self._repo.filter(embedding=None)
        return items[:limit]

    async def delete(self, uuid: UUID) -> bool:
        item = await self.get_by_uuid(uuid)
        result = await self._repo.delete_by_id(item.id)

        if result:
            await self._delete_cached(
                self._cache_key_by_id(item.id),
                self._cache_key_uuid_to_id(uuid),
            )
            await self._invalidate_list_cache()
            logger.info(f"Deleted knowledge item: uuid={uuid}")

        return result
