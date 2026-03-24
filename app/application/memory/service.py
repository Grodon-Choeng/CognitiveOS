from datetime import UTC, datetime

from app.application.conversations.ports import ConversationContextResolver
from app.application.memory.commands import ArchiveMemoryCommand, CreateMemoryCommand
from app.application.memory.dto import MemoryDTO, MemoryListDTO
from app.application.memory.errors import MemoryNotFoundError, MemoryStateConflictError
from app.application.memory.ports import MemoryUnitOfWorkFactory
from app.application.memory.queries import ListMemoriesQuery
from app.domain.memory.entities import MemoryEntry, MemoryStatus, MemoryType
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
            memory_type=_resolve_memory_type(command.memory_type, command.content),
            conversation_id=conversation_context.conversation_id,
            session_id=conversation_context.session_id,
            scope_object_type=command.scope_object_type,
            scope_object_id=command.scope_object_id,
            importance=_normalize_importance(command.importance),
            expires_at=command.expires_at,
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
                query=query.query,
                limit=query.limit,
            )

        return MemoryListDTO(items=[self._to_dto(memory) for memory in memories])

    async def find_candidates(
        self,
        *,
        conversation_id: str,
        session_id: str,
        query: str | None = None,
        limit: int = 5,
    ) -> MemoryListDTO:
        return await self.list_memories(
            ListMemoriesQuery(
                conversation_id=conversation_id,
                session_id=session_id,
                status=MemoryStatus.ACTIVE.value,
                query=query,
                limit=limit,
            )
        )

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

    async def archive_latest_memory(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> MemoryDTO:
        memory_list = await self.list_memories(
            ListMemoriesQuery(
                conversation_id=conversation_id,
                session_id=session_id,
                status=MemoryStatus.ACTIVE.value,
                limit=1,
            )
        )
        if not memory_list.items:
            raise MemoryNotFoundError("当前会话没有可归档的记忆。")
        return await self.archive_memory(
            ArchiveMemoryCommand(memory_id=memory_list.items[0].memory_id)
        )

    async def archive_matching_memory(
        self,
        *,
        conversation_id: str,
        session_id: str,
        content_hint: str,
    ) -> MemoryDTO:
        memory_list = await self.list_memories(
            ListMemoriesQuery(
                conversation_id=conversation_id,
                session_id=session_id,
                status=MemoryStatus.ACTIVE.value,
                limit=20,
            )
        )
        normalized_hint = content_hint.casefold()
        for memory in memory_list.items:
            if normalized_hint in memory.content.casefold():
                return await self.archive_memory(ArchiveMemoryCommand(memory_id=memory.memory_id))
        raise MemoryNotFoundError(f"当前会话没有匹配“{content_hint}”的记忆。")

    @staticmethod
    def _to_dto(memory: MemoryEntry) -> MemoryDTO:
        return MemoryDTO(
            memory_id=str(memory.memory_id.value),
            content=memory.content,
            created_at=memory.created_at,
            status=memory.status.value,
            memory_type=memory.memory_type.value,
            conversation_id=memory.conversation_id,
            session_id=memory.session_id,
            scope_object_type=memory.scope_object_type,
            scope_object_id=memory.scope_object_id,
            importance=memory.importance,
            expires_at=memory.expires_at,
            archived_at=memory.archived_at,
        )


def _resolve_memory_type(memory_type: str | None, content: str) -> MemoryType:
    if memory_type:
        return MemoryType(memory_type)
    normalized_content = content.casefold()
    if "临时" in normalized_content:
        return MemoryType.TEMPORARY
    if (
        "偏好" in normalized_content
        or "喜欢" in normalized_content
        or "不喜欢" in normalized_content
    ):
        return MemoryType.PREFERENCE
    if "背景" in normalized_content:
        return MemoryType.CONTEXT
    return MemoryType.NOTE


def _normalize_importance(importance: int) -> int:
    if importance < 1:
        return 1
    if importance > 5:
        return 5
    return importance
