from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.memory.ports import MemoryUnitOfWork
from app.application.reminders.ports import ReminderUnitOfWork
from app.infrastructure.db.repositories.memory_repository import SQLAlchemyMemoryRepository
from app.infrastructure.db.repositories.reminder_repository import SQLAlchemyReminderRepository


class SQLAlchemyReminderUnitOfWork(ReminderUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session = session_factory()
        self.reminders = SQLAlchemyReminderRepository(self.session)

    async def __aenter__(self) -> "SQLAlchemyReminderUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _ = tb
        if exc_type is not None:
            await self.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


class SQLAlchemyMemoryUnitOfWork(MemoryUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session = session_factory()
        self.memories = SQLAlchemyMemoryRepository(self.session)

    async def __aenter__(self) -> "SQLAlchemyMemoryUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _ = tb
        if exc_type is not None:
            await self.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()
