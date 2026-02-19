from contextlib import asynccontextmanager
from typing import Generic, TypeVar, Optional, Type, Any, List, cast, AsyncIterator

from piccolo.columns import Column
from piccolo.engine import Engine

from .model import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):
    def __init__(self, model: Type[T]):
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

    async def get_by_id(self, id_value: int) -> Optional[T]:
        return await self.model.objects().where(self.get_col("id") == id_value).first()

    async def get_by_uuid(self, uuid_value: Any) -> Optional[T]:
        if not hasattr(self.model, "uuid"):
            raise AttributeError(f"{self.model.__name__} has no 'uuid' field")

        return (
            await self.model.objects().where(self.get_col("uuid") == uuid_value).first()
        )

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

    async def filter(self, **filters: Any) -> List[T]:
        query = self.model.objects()
        for key, value in filters.items():
            query = query.where(self.get_col(key) == value)
        return await query.run()

    async def list(
        self,
        limit: int = 20,
        offset: int = 0,
        order_by: Optional[Any] = None,
    ) -> List[T]:
        query = self.model.objects().limit(limit).offset(offset)
        if order_by is not None:
            query = query.order_by(order_by)
        return await query.run()

    async def create(self, **kwargs: Any) -> T:
        instance = self.model(**kwargs)
        await instance.save()
        return instance

    async def bulk_create(self, data: List[dict[str, Any]]) -> List[T]:
        instances = [self.model(**item) for item in data]
        await self.model.insert(*instances)
        return instances

    @staticmethod
    async def update(instance: T, **kwargs: Any) -> T:
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await instance.save()
        return instance

    async def update_by_id(self, id_value: int, **kwargs: Any) -> Optional[T]:
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
