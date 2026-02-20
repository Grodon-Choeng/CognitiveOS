from typing import Any, Protocol

from cashews import cache

from app.config import settings


class Cacheable(Protocol):
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Cacheable": ...


async def get_cached_model[T: Cacheable](model_class: type[T], key: str) -> T | None:
    data = await cache.get(key)
    if data is not None:
        return model_class.from_dict(data)
    return None


async def set_cached_model[T: Cacheable](item: T, key: str, ttl: int | None = None) -> None:
    await cache.set(key, item.to_dict(), expire=ttl or settings.cache_default_ttl)


async def get_cached_models[T: Cacheable](
    model_class: type[T],
    keys: list[str],
) -> list[T | None]:
    if not keys:
        return []

    results = await cache.get_many(*keys)
    return [model_class.from_dict(data) if data is not None else None for data in results]


async def set_cached_models[T: Cacheable](
    items: list[T],
    keys: list[str],
    ttl: int | None = None,
) -> None:
    if not items or not keys:
        return

    data_map = {key: item.to_dict() for key, item in zip(keys, items, strict=False)}
    await cache.set_many(data_map, expire=ttl or settings.cache_default_ttl)


async def delete_cached_keys(*keys: str) -> None:
    for key in keys:
        await cache.delete(key)


async def delete_cached_pattern(pattern: str) -> None:
    await cache.delete_match(pattern)
