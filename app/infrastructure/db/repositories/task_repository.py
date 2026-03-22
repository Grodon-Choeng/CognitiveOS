from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.tasks.entities import Task, TaskStatus
from app.domain.tasks.repository import TaskRepository
from app.domain.tasks.value_objects import TaskId
from app.infrastructure.db.models.task import TaskModel


class SQLAlchemyTaskRepository(TaskRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, task: Task) -> None:
        self.session.add(self._to_model(task))

    async def get(self, task_id: TaskId) -> Task | None:
        statement = select(TaskModel).where(TaskModel.id == str(task_id.value))
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
        query: str | None = None,
        limit: int = 20,
    ) -> list[Task]:
        statement = select(TaskModel).order_by(TaskModel.created_at.desc()).limit(limit)
        if conversation_id is not None:
            statement = statement.where(TaskModel.conversation_id == conversation_id)
        if session_id is not None:
            statement = statement.where(TaskModel.session_id == session_id)
        if status is not None:
            statement = statement.where(TaskModel.status == status)
        if query is not None:
            statement = statement.where(TaskModel.title.ilike(f"%{query}%"))

        models = (await self.session.execute(statement)).scalars().all()
        return [self._to_domain(model) for model in models]

    async def update(self, task: Task) -> None:
        model = await self.session.get(TaskModel, str(task.task_id.value))
        if model is None:
            self.session.add(self._to_model(task))
            return

        model.title = task.title
        model.status = task.status.value
        model.conversation_id = task.conversation_id
        model.session_id = task.session_id
        model.completed_at = task.completed_at

    @staticmethod
    def _to_model(task: Task) -> TaskModel:
        return TaskModel(
            id=str(task.task_id.value),
            title=task.title,
            status=task.status.value,
            conversation_id=task.conversation_id,
            session_id=task.session_id,
            completed_at=task.completed_at,
            created_at=task.created_at,
        )

    @staticmethod
    def _to_domain(model: TaskModel) -> Task:
        return Task(
            task_id=TaskId.from_string(model.id),
            title=model.title,
            created_at=model.created_at,
            status=TaskStatus(model.status),
            conversation_id=model.conversation_id,
            session_id=model.session_id,
            completed_at=model.completed_at,
        )
