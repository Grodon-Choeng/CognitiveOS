from datetime import UTC, datetime

from app.application.conversations.ports import ConversationContextResolver
from app.application.memory.commands import ArchiveMemoryCommand, CreateMemoryCommand
from app.application.memory.dto import MemoryDTO, MemoryListDTO
from app.application.memory.errors import MemoryNotFoundError, MemoryStateConflictError
from app.application.memory.ports import MemoryUnitOfWorkFactory
from app.application.memory.queries import ListMemoriesQuery
from app.domain.memory.entities import MemoryEntry, MemoryStatus
from app.domain.memory.value_objects import MemoryId


class MemoryApplicationService:
    def __init__(
        self,
        unit_of_work_factory: MemoryUnitOfWorkFactory,
        conversation_context_resolver: ConversationContextResolver,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.conversation_context_resolver = conversation_context_resolver

    async def create_memory(self, command: CreateMemoryCommand) -> MemoryDTO:
        conversation_context = await self.conversation_context_resolver.resolve_for_outbound(
            provided_conversation_id=command.conversation_id,
            provided_session_id=command.session_id,
            source_channel=command.source_channel,
            source_user_id=command.source_user_id,
            source_chat_id=command.source_chat_id,
            source_thread_id=command.source_thread_id,
        )
        memory = MemoryEntry(
            memory_id=MemoryId.new(),
            content=command.content,
            created_at=datetime.now(UTC),
            conversation_id=conversation_context.conversation_id,
            session_id=conversation_context.session_id,
        )

        async with self.unit_of_work_factory() as unit_of_work:
            await unit_of_work.memories.add(memory)
            await unit_of_work.commit()

        return self._to_dto(memory)

    async def get_memory(self, memory_id: str) -> MemoryDTO:
        parsed_memory_id = MemoryId.from_string(memory_id)

        async with self.unit_of_work_factory() as unit_of_work:
            memory = await unit_of_work.memories.get(parsed_memory_id)
            if memory is None:
                raise MemoryNotFoundError(f"记忆不存在：{memory_id}")

        return self._to_dto(memory)

    async def list_memories(self, query: ListMemoriesQuery) -> MemoryListDTO:
        async with self.unit_of_work_factory() as unit_of_work:
            memories = await unit_of_work.memories.list(
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                status=query.status or MemoryStatus.ACTIVE.value,
                limit=query.limit,
            )

        return MemoryListDTO(items=[self._to_dto(memory) for memory in memories])

    async def archive_memory(self, command: ArchiveMemoryCommand) -> MemoryDTO:
        parsed_memory_id = MemoryId.from_string(command.memory_id)

        async with self.unit_of_work_factory() as unit_of_work:
            memory = await unit_of_work.memories.get(parsed_memory_id)
            if memory is None:
                raise MemoryNotFoundError(f"记忆不存在：{command.memory_id}")
            if memory.status == MemoryStatus.ARCHIVED:
                return self._to_dto(memory)

            if memory.status != MemoryStatus.ACTIVE:
                raise MemoryStateConflictError(f"记忆当前状态不允许归档：{memory.status.value}")

            memory.status = MemoryStatus.ARCHIVED
            memory.archived_at = datetime.now(UTC)
            await unit_of_work.memories.update(memory)
            await unit_of_work.commit()

        return self._to_dto(memory)

    @staticmethod
    def _to_dto(memory: MemoryEntry) -> MemoryDTO:
        return MemoryDTO(
            memory_id=str(memory.memory_id.value),
            content=memory.content,
            created_at=memory.created_at,
            status=memory.status.value,
            conversation_id=memory.conversation_id,
            session_id=memory.session_id,
            archived_at=memory.archived_at,
        )
