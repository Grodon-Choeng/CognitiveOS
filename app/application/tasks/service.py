from datetime import UTC, datetime

from app.application.conversations.ports import ConversationContextResolver
from app.application.tasks.commands import CompleteTaskCommand, CreateTaskCommand
from app.application.tasks.dto import TaskDTO, TaskListDTO
from app.application.tasks.errors import TaskNotFoundError, TaskStateConflictError
from app.application.tasks.ports import TaskUnitOfWorkFactory
from app.application.tasks.queries import ListTasksQuery
from app.domain.tasks.entities import Task, TaskStatus
from app.domain.tasks.value_objects import TaskId


class TaskApplicationService:
    def __init__(
        self,
        unit_of_work_factory: TaskUnitOfWorkFactory,
        conversation_context_resolver: ConversationContextResolver,
    ) -> None:
        self.unit_of_work_factory = unit_of_work_factory
        self.conversation_context_resolver = conversation_context_resolver

    async def create_task(self, command: CreateTaskCommand) -> TaskDTO:
        conversation_context = await self.conversation_context_resolver.resolve_for_outbound(
            provided_conversation_id=command.conversation_id,
            provided_session_id=command.session_id,
            source_channel=command.source_channel,
            source_user_id=command.source_user_id,
            source_chat_id=command.source_chat_id,
            source_thread_id=command.source_thread_id,
        )
        task = Task(
            task_id=TaskId.new(),
            title=command.title,
            created_at=datetime.now(UTC),
            conversation_id=conversation_context.conversation_id,
            session_id=conversation_context.session_id,
        )

        async with self.unit_of_work_factory() as unit_of_work:
            await unit_of_work.tasks.add(task)
            await unit_of_work.commit()

        return self._to_dto(task)

    async def get_task(self, task_id: str) -> TaskDTO:
        parsed_task_id = TaskId.from_string(task_id)

        async with self.unit_of_work_factory() as unit_of_work:
            task = await unit_of_work.tasks.get(parsed_task_id)
            if task is None:
                raise TaskNotFoundError(f"任务不存在：{task_id}")

        return self._to_dto(task)

    async def list_tasks(self, query: ListTasksQuery) -> TaskListDTO:
        async with self.unit_of_work_factory() as unit_of_work:
            tasks = await unit_of_work.tasks.list(
                conversation_id=query.conversation_id,
                session_id=query.session_id,
                status=query.status,
                limit=query.limit,
            )

        return TaskListDTO(items=[self._to_dto(task) for task in tasks])

    async def complete_task(self, command: CompleteTaskCommand) -> TaskDTO:
        parsed_task_id = TaskId.from_string(command.task_id)

        async with self.unit_of_work_factory() as unit_of_work:
            task = await unit_of_work.tasks.get(parsed_task_id)
            if task is None:
                raise TaskNotFoundError(f"任务不存在：{command.task_id}")
            if task.status == TaskStatus.COMPLETED:
                return self._to_dto(task)
            if task.status != TaskStatus.PENDING:
                raise TaskStateConflictError(f"任务当前状态不允许完成：{task.status.value}")

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(UTC)
            await unit_of_work.tasks.update(task)
            await unit_of_work.commit()

        return self._to_dto(task)

    @staticmethod
    def _to_dto(task: Task) -> TaskDTO:
        return TaskDTO(
            task_id=str(task.task_id.value),
            title=task.title,
            created_at=task.created_at,
            status=task.status.value,
            conversation_id=task.conversation_id,
            session_id=task.session_id,
            completed_at=task.completed_at,
        )
