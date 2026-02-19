import builtins
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast

from piccolo.columns import Column
from piccolo.engine import Engine

from app.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.enums import SortField, SortOrder

from .model import BaseModel


@dataclass
class CursorPage[T]:
    items: list[T]
    next_cursor: str | None
    has_more: bool


class BaseRepository[T: BaseModel]:
    def __init__(self, model: type[T]) -> None:
        self.model = model

    @property
    def _engine(self) -> Engine:
        return self.model._meta.db

    def get_col(self, col: str) -> Column:
        return cast(Column, getattr(self.model, col))

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        async with self._engine.transaction():
            yield

    async def get_by_id(self, id_value: int) -> T | None:
        return await self.model.objects().where(self.get_col("id") == id_value).first()

    async def get_by_uuid(self, uuid_value: Any) -> T | None:
        if not hasattr(self.model, "uuid"):
            raise AttributeError(f"{self.model.__name__} has no 'uuid' field")

        return await self.model.objects().where(self.get_col("uuid") == uuid_value).first()

    async def exists(self, **filters: Any) -> bool:
        query = self.model.objects()
        for key, value in filters.items():
            query = query.where(self.get_col(key) == value)

        return bool(await query.select(1).first())

    async def count(self, **filters: Any) -> int:
        query = self.model.objects()
        for key, value in filters.items():
            query = query.where(self.get_col(key) == value)
        return await query.count()

    async def filter(self, **filters: Any) -> list[T]:
        query = self.model.objects()
        for key, value in filters.items():
            query = query.where(self.get_col(key) == value)
        return await query.run()

    async def list(
        self,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
        order_by: Any | None = None,
    ) -> list[T]:
        limit = min(limit, MAX_PAGE_SIZE)
        query = self.model.objects().limit(limit).offset(offset)
        if order_by is not None:
            query = query.order_by(order_by)
        return await query.run()

    async def cursor_paginate(
        self,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
        sort_field: SortField = SortField.CREATED_AT,
        sort_order: SortOrder = SortOrder.DESC,
    ) -> CursorPage[T]:
        limit = min(limit, MAX_PAGE_SIZE)
        sort_col = self.get_col(sort_field.value)
        id_col = self.get_col("id")

        is_desc = sort_order == SortOrder.DESC

        query = self.model.objects()

        if cursor:
            cursor_record = await self.get_by_uuid(cursor)
            if cursor_record:
                cursor_id = cursor_record.id
                cursor_value = getattr(cursor_record, sort_field.value, None)

                if cursor_value:
                    if is_desc:
                        query = query.where(
                            (sort_col < cursor_value)
                            | ((sort_col == cursor_value) & (id_col < cursor_id))
                        )
                    else:
                        query = query.where(
                            (sort_col > cursor_value)
                            | ((sort_col == cursor_value) & (id_col > cursor_id))
                        )

        query = query.order_by(sort_col, id_col, ascending=not is_desc)

        fetch_limit = limit + 1
        query = query.limit(fetch_limit)

        items = await query.run()

        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        next_cursor = None
        if items and has_more:
            last_item = items[-1]
            next_cursor = str(last_item.uuid)

        return CursorPage(items=items, next_cursor=next_cursor, has_more=has_more)

    async def create(self, **kwargs: Any) -> T:
        instance = self.model(**kwargs)
        await instance.save()
        return instance

    async def bulk_create(self, data: builtins.list[dict[str, Any]]) -> builtins.list[T]:
        instances = [self.model(**item) for item in data]
        await self.model.insert(*instances)
        return instances

    @staticmethod
    async def update(instance: T, **kwargs: Any) -> T:
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await instance.save()
        return instance

    async def update_by_id(self, id_value: int, **kwargs: Any) -> T | None:
        instance = await self.get_by_id(id_value)
        if not instance:
            return None
        return await self.update(instance, **kwargs)

    @staticmethod
    async def delete(instance: T) -> bool:
        await instance.remove()
        return True

    async def delete_by_id(self, id_value: int) -> bool:
        instance = await self.get_by_id(id_value)
        if not instance:
            return False
        await instance.remove()
        return True
