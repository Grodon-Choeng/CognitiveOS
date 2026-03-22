from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.memory.entities import MemoryEntry, MemoryStatus
from app.domain.memory.repository import MemoryRepository
from app.domain.memory.value_objects import MemoryId
from app.infrastructure.db.models.memory import MemoryModel


class SQLAlchemyMemoryRepository(MemoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, memory: MemoryEntry) -> None:
        self.session.add(self._to_model(memory))

    async def get(self, memory_id: MemoryId) -> MemoryEntry | None:
        statement = select(MemoryModel).where(MemoryModel.id == str(memory_id.value))
        model = (await self.session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None
        return self._to_domain(model)

    async def list(
        self,
        *,
        conversation_id: str | None = None,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        statement = select(MemoryModel).order_by(MemoryModel.created_at.desc()).limit(limit)
        if conversation_id is not None:
            statement = statement.where(MemoryModel.conversation_id == conversation_id)
        if session_id is not None:
            statement = statement.where(MemoryModel.session_id == session_id)
        if status is not None:
            statement = statement.where(MemoryModel.status == status)

        models = (await self.session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    async def update(self, memory: MemoryEntry) -> None:
        model = await self.session.get(MemoryModel, str(memory.memory_id.value))
        if model is None:
            self.session.add(self._to_model(memory))
            return

        model.content = memory.content
        model.status = memory.status.value
        model.conversation_id = memory.conversation_id
        model.session_id = memory.session_id
        model.archived_at = memory.archived_at

    @staticmethod
    def _to_model(memory: MemoryEntry) -> MemoryModel:
        return MemoryModel(
            id=str(memory.memory_id.value),
            content=memory.content,
            status=memory.status.value,
            conversation_id=memory.conversation_id,
            session_id=memory.session_id,
            archived_at=memory.archived_at,
            created_at=memory.created_at,
        )

    @staticmethod
    def _to_domain(model: MemoryModel) -> MemoryEntry:
        return MemoryEntry(
            memory_id=MemoryId.from_string(model.id),
            content=model.content,
            created_at=model.created_at,
            status=MemoryStatus(model.status),
            conversation_id=model.conversation_id,
            session_id=model.session_id,
            archived_at=model.archived_at,
        )
