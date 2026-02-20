from typing import Any, TypeVar

from app.config import settings
from app.core.model import BaseModel
from app.core.repository import BaseRepository
from app.utils.cache import (
    delete_cached_keys,
    delete_cached_pattern,
    get_cached_model,
    get_cached_models,
    set_cached_model,
)
from app.utils.logging import logger

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R", bound=BaseRepository)


class BaseService[T: BaseModel, R: BaseRepository]:
    cache_prefix: str = ""
    cache_ttl: int = settings.cache_default_ttl

    def __init__(self, repo: R) -> None:
        self._repo = repo

    def _cache_key(self, *parts: Any) -> str:
        return ":".join([self.cache_prefix, *map(str, parts)])

    def _cache_key_by_id(self, item_id: int) -> str:
        return self._cache_key("id", item_id)

    def _cache_key_list(self, *args: Any) -> str:
        return self._cache_key("list", *args)

    async def _get_cached(self, model_class: type[T], key: str) -> T | None:
        cached = await get_cached_model(model_class, key)
        if cached is not None:
            logger.debug(f"Cache hit: {key}")
        return cached

    async def _set_cached(self, item: T, key: str, ttl: int | None = None) -> None:
        await set_cached_model(item, key, ttl or self.cache_ttl)
        logger.debug(f"Cache set: {key}")

    async def _get_cached_batch(self, model_class: type[T], keys: list[str]) -> list[T | None]:
        return await get_cached_models(model_class, keys)

    async def _delete_cached(self, *keys: str) -> None:
        await delete_cached_keys(*keys)
        for key in keys:
            logger.debug(f"Cache deleted: {key}")

    async def _delete_cached_pattern(self, pattern: str) -> None:
        full_pattern = self._cache_key(pattern, "*")
        await delete_cached_pattern(full_pattern)
        logger.debug(f"Cache pattern deleted: {full_pattern}")

    async def _invalidate_list_cache(self) -> None:
        await self._delete_cached_pattern("list")

    async def _cache_item(self, item: T) -> None:
        await self._set_cached(item, self._cache_key_by_id(item.id))

    async def _invalidate_item_cache(self, item_id: int) -> None:
        await self._delete_cached(self._cache_key_by_id(item_id))
