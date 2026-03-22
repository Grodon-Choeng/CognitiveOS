from collections.abc import Callable
from types import TracebackType

import pytest

from app.application.conversations.ports import (
    ConversationContextResolver,
    ResolvedConversationContext,
)
from app.application.memory.commands import ArchiveMemoryCommand, CreateMemoryCommand
from app.application.memory.errors import MemoryNotFoundError
from app.application.memory.ports import MemoryUnitOfWork
from app.application.memory.queries import ListMemoriesQuery
from app.application.memory.service import MemoryApplicationService
from app.domain.memory.entities import MemoryEntry, MemoryStatus
from app.domain.memory.repository import MemoryRepository
from app.domain.memory.value_objects import MemoryId


class FakeMemoryRepository(MemoryRepository):
    def __init__(self) -> None:
        self.items: dict[str, MemoryEntry] = {}

    async def add(self, memory: MemoryEntry) -> None:
        self.items[str(memory.memory_id.value)] = memory

    async def get(self, memory_id: MemoryId) -> MemoryEntry | None:
        return self.items.get(str(memory_id.value))

    async def list(
        self,
        *,
        conversation_id: str | None = None,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[MemoryEntry]:
        memories = list(self.items.values())
        memories.sort(key=lambda memory: memory.created_at, reverse=True)
        if conversation_id is not None:
            memories = [memory for memory in memories if memory.conversation_id == conversation_id]
        if session_id is not None:
            memories = [memory for memory in memories if memory.session_id == session_id]
        if status is not None:
            memories = [memory for memory in memories if memory.status.value == status]
        return memories[:limit]

    async def update(self, memory: MemoryEntry) -> None:
        self.items[str(memory.memory_id.value)] = memory


class FakeMemoryUnitOfWork(MemoryUnitOfWork):
    def __init__(self, repository: FakeMemoryRepository) -> None:
        self.memories: MemoryRepository = repository
        self.commit_count = 0

    async def __aenter__(self) -> "FakeMemoryUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc, tb)

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        return None


class FakeConversationContextResolver(ConversationContextResolver):
    async def resolve_for_outbound(
        self,
        *,
        provided_conversation_id: str | None,
        provided_session_id: str | None,
        source_channel: str | None,
        source_user_id: str | None,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext:
        _ = (source_channel, source_user_id, source_chat_id, source_thread_id)
        return ResolvedConversationContext(
            conversation_id=provided_conversation_id or "conversation-test",
            session_id=provided_session_id or "session-test",
        )

    async def resolve_for_inbound(
        self,
        *,
        source_channel: str,
        source_user_id: str,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext:
        _ = (source_channel, source_user_id, source_chat_id, source_thread_id)
        return ResolvedConversationContext(
            conversation_id="conversation-test",
            session_id="session-test",
        )


def create_fake_unit_of_work_factory(
    repository: FakeMemoryRepository,
) -> Callable[[], FakeMemoryUnitOfWork]:
    def factory() -> FakeMemoryUnitOfWork:
        return FakeMemoryUnitOfWork(repository)

    return factory


@pytest.mark.asyncio
async def test_create_memory_persists_memory() -> None:
    repository = FakeMemoryRepository()
    service = MemoryApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    result = await service.create_memory(
        CreateMemoryCommand(
            content="用户偏好：喜欢早上九点收到提醒",
            conversation_id="conversation-1",
        )
    )

    saved = repository.items[result.memory_id]
    assert saved.content == "用户偏好：喜欢早上九点收到提醒"
    assert saved.conversation_id == "conversation-1"
    assert result.session_id == "session-test"
    assert result.status == "active"


@pytest.mark.asyncio
async def test_get_memory_returns_existing_memory() -> None:
    repository = FakeMemoryRepository()
    service = MemoryApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    created = await service.create_memory(CreateMemoryCommand(content="用户偏好：只接收飞书通知"))

    fetched = await service.get_memory(created.memory_id)

    assert fetched.memory_id == created.memory_id
    assert fetched.content == "用户偏好：只接收飞书通知"


@pytest.mark.asyncio
async def test_get_memory_raises_when_missing() -> None:
    repository = FakeMemoryRepository()
    service = MemoryApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    with pytest.raises(MemoryNotFoundError):
        await service.get_memory("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_list_memories_returns_filtered_items() -> None:
    repository = FakeMemoryRepository()
    service = MemoryApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    first = await service.create_memory(
        CreateMemoryCommand(
            content="第一条记忆",
            conversation_id="conversation-1",
            session_id="session-1",
        )
    )
    await service.create_memory(
        CreateMemoryCommand(
            content="第二条记忆",
            conversation_id="conversation-2",
            session_id="session-2",
        )
    )

    result = await service.list_memories(
        ListMemoriesQuery(conversation_id="conversation-1", limit=10)
    )

    assert [item.memory_id for item in result.items] == [first.memory_id]


@pytest.mark.asyncio
async def test_archive_memory_updates_status() -> None:
    repository = FakeMemoryRepository()
    service = MemoryApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    created = await service.create_memory(CreateMemoryCommand(content="需要归档的记忆"))

    archived = await service.archive_memory(ArchiveMemoryCommand(memory_id=created.memory_id))

    assert archived.status == "archived"
    assert repository.items[created.memory_id].status == MemoryStatus.ARCHIVED
    assert repository.items[created.memory_id].archived_at is not None


@pytest.mark.asyncio
async def test_archive_memory_is_idempotent_for_archived_memory() -> None:
    repository = FakeMemoryRepository()
    service = MemoryApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    created = await service.create_memory(CreateMemoryCommand(content="需要归档的记忆"))
    repository.items[created.memory_id].status = MemoryStatus.ARCHIVED

    archived = await service.archive_memory(ArchiveMemoryCommand(memory_id=created.memory_id))

    assert archived.status == "archived"


@pytest.mark.asyncio
async def test_list_memories_defaults_to_active_only() -> None:
    repository = FakeMemoryRepository()
    service = MemoryApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    active = await service.create_memory(CreateMemoryCommand(content="活跃记忆"))
    archived = await service.create_memory(CreateMemoryCommand(content="归档记忆"))
    repository.items[archived.memory_id].status = MemoryStatus.ARCHIVED
    repository.items[archived.memory_id].archived_at = repository.items[
        archived.memory_id
    ].created_at

    result = await service.list_memories(ListMemoriesQuery(limit=10))

    assert [item.memory_id for item in result.items] == [active.memory_id]
