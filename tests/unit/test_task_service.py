from collections.abc import Callable
from types import TracebackType

import pytest

from app.application.conversations.ports import (
    ConversationContextResolver,
    ResolvedConversationContext,
)
from app.application.tasks.commands import CancelTaskCommand, CompleteTaskCommand, CreateTaskCommand
from app.application.tasks.errors import TaskNotFoundError, TaskStateConflictError
from app.application.tasks.ports import TaskUnitOfWork
from app.application.tasks.queries import ListTasksQuery
from app.application.tasks.service import TaskApplicationService
from app.domain.tasks.entities import Task, TaskStatus
from app.domain.tasks.repository import TaskRepository
from app.domain.tasks.value_objects import TaskId


class FakeTaskRepository(TaskRepository):
    def __init__(self) -> None:
        self.items: dict[str, Task] = {}

    async def add(self, task: Task) -> None:
        self.items[str(task.task_id.value)] = task

    async def get(self, task_id: TaskId) -> Task | None:
        return self.items.get(str(task_id.value))

    async def list(
        self,
        *,
        conversation_id: str | None = None,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[Task]:
        tasks = list(self.items.values())
        tasks.sort(key=lambda task: task.created_at, reverse=True)
        if conversation_id is not None:
            tasks = [task for task in tasks if task.conversation_id == conversation_id]
        if session_id is not None:
            tasks = [task for task in tasks if task.session_id == session_id]
        if status is not None:
            tasks = [task for task in tasks if task.status.value == status]
        return tasks[:limit]

    async def update(self, task: Task) -> None:
        self.items[str(task.task_id.value)] = task


class FakeTaskUnitOfWork(TaskUnitOfWork):
    def __init__(self, repository: FakeTaskRepository) -> None:
        self.tasks: TaskRepository = repository
        self.commit_count = 0

    async def __aenter__(self) -> "FakeTaskUnitOfWork":
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
    repository: FakeTaskRepository,
) -> Callable[[], FakeTaskUnitOfWork]:
    def factory() -> FakeTaskUnitOfWork:
        return FakeTaskUnitOfWork(repository)

    return factory


@pytest.mark.asyncio
async def test_create_task_persists_task() -> None:
    repository = FakeTaskRepository()
    service = TaskApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    result = await service.create_task(CreateTaskCommand(title="整理今天的会议纪要"))

    saved = repository.items[result.task_id]
    assert saved.title == "整理今天的会议纪要"
    assert result.status == "pending"


@pytest.mark.asyncio
async def test_get_task_returns_existing_task() -> None:
    repository = FakeTaskRepository()
    service = TaskApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    created = await service.create_task(CreateTaskCommand(title="整理今天的会议纪要"))

    fetched = await service.get_task(created.task_id)

    assert fetched.task_id == created.task_id


@pytest.mark.asyncio
async def test_get_task_raises_when_missing() -> None:
    repository = FakeTaskRepository()
    service = TaskApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )

    with pytest.raises(TaskNotFoundError):
        await service.get_task("00000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_list_tasks_returns_filtered_items() -> None:
    repository = FakeTaskRepository()
    service = TaskApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    first = await service.create_task(
        CreateTaskCommand(title="第一项任务", conversation_id="conversation-1")
    )
    second = await service.create_task(
        CreateTaskCommand(title="第二项任务", conversation_id="conversation-2")
    )
    repository.items[second.task_id].status = TaskStatus.CANCELED

    result = await service.list_tasks(ListTasksQuery(conversation_id="conversation-1", limit=10))

    assert [item.task_id for item in result.items] == [first.task_id]


@pytest.mark.asyncio
async def test_complete_task_updates_status() -> None:
    repository = FakeTaskRepository()
    service = TaskApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    created = await service.create_task(CreateTaskCommand(title="整理今天的会议纪要"))

    completed = await service.complete_task(CompleteTaskCommand(task_id=created.task_id))

    assert completed.status == "completed"
    assert repository.items[created.task_id].completed_at is not None


@pytest.mark.asyncio
async def test_complete_task_rejects_non_pending_task() -> None:
    repository = FakeTaskRepository()
    service = TaskApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    created = await service.create_task(CreateTaskCommand(title="整理今天的会议纪要"))
    repository.items[created.task_id].status = TaskStatus.CANCELED

    with pytest.raises(TaskStateConflictError):
        await service.complete_task(CompleteTaskCommand(task_id=created.task_id))


@pytest.mark.asyncio
async def test_cancel_task_updates_status() -> None:
    repository = FakeTaskRepository()
    service = TaskApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    created = await service.create_task(CreateTaskCommand(title="整理今天的会议纪要"))

    canceled = await service.cancel_task(CancelTaskCommand(task_id=created.task_id))

    assert canceled.status == "canceled"
    assert repository.items[created.task_id].status == TaskStatus.CANCELED


@pytest.mark.asyncio
async def test_cancel_task_is_idempotent_for_already_canceled_task() -> None:
    repository = FakeTaskRepository()
    service = TaskApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    created = await service.create_task(CreateTaskCommand(title="整理今天的会议纪要"))
    repository.items[created.task_id].status = TaskStatus.CANCELED

    canceled = await service.cancel_task(CancelTaskCommand(task_id=created.task_id))

    assert canceled.status == "canceled"


@pytest.mark.asyncio
async def test_cancel_task_rejects_non_pending_task() -> None:
    repository = FakeTaskRepository()
    service = TaskApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    created = await service.create_task(CreateTaskCommand(title="整理今天的会议纪要"))
    repository.items[created.task_id].status = TaskStatus.COMPLETED

    with pytest.raises(TaskStateConflictError):
        await service.cancel_task(CancelTaskCommand(task_id=created.task_id))


@pytest.mark.asyncio
async def test_complete_latest_task_uses_latest_pending_task() -> None:
    repository = FakeTaskRepository()
    service = TaskApplicationService(
        unit_of_work_factory=create_fake_unit_of_work_factory(repository),
        conversation_context_resolver=FakeConversationContextResolver(),
    )
    older = await service.create_task(
        CreateTaskCommand(title="旧任务", conversation_id="conversation-1", session_id="session-1")
    )
    latest = await service.create_task(
        CreateTaskCommand(title="新任务", conversation_id="conversation-1", session_id="session-1")
    )

    completed = await service.complete_latest_task(
        conversation_id="conversation-1",
        session_id="session-1",
    )

    assert completed.task_id == latest.task_id
    assert repository.items[older.task_id].status == TaskStatus.PENDING
    assert repository.items[latest.task_id].status == TaskStatus.COMPLETED
