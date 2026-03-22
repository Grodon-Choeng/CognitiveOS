from typing import Protocol

from app.domain.tasks.entities import Task
from app.domain.tasks.value_objects import TaskId


class TaskRepository(Protocol):
    async def add(self, task: Task) -> None: ...

    async def get(self, task_id: TaskId) -> Task | None: ...

    async def list(
        self,
        *,
        conversation_id: str | None = None,
        session_id: str | None = None,
        status: str | None = None,
        query: str | None = None,
        limit: int = 20,
    ) -> list[Task]: ...

    async def update(self, task: Task) -> None: ...
