from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.http.deps import TaskServiceDep
from app.api.http.schemas.common import ErrorResponse
from app.api.http.schemas.task import (
    CreateTaskRequest,
    TaskListResponse,
    TaskResponse,
    TaskStatusFilter,
)
from app.application.tasks.commands import CancelTaskCommand, CompleteTaskCommand, CreateTaskCommand
from app.application.tasks.queries import ListTasksQuery

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=TaskResponse,
    response_model_exclude_none=True,
    summary="创建任务",
)
async def create_task(
    payload: CreateTaskRequest,
    service: TaskServiceDep,
) -> TaskResponse:
    result = await service.create_task(
        CreateTaskCommand(
            title=payload.title,
            linked_reminder_id=payload.linked_reminder_id,
            source_type=payload.source_type,
            source_id=payload.source_id,
            conversation_id=payload.conversation_id,
            session_id=payload.session_id,
            source_channel=payload.source_channel,
            source_user_id=payload.source_user_id,
            source_chat_id=payload.source_chat_id,
            source_thread_id=payload.source_thread_id,
        )
    )
    return TaskResponse(**asdict(result))


@router.get(
    "",
    response_model=TaskListResponse,
    response_model_exclude_none=True,
    summary="查询任务列表",
)
async def list_tasks(
    service: TaskServiceDep,
    conversation_id: str | None = None,
    session_id: str | None = None,
    status: TaskStatusFilter | None = None,
    query: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TaskListResponse:
    result = await service.list_tasks(
        ListTasksQuery(
            conversation_id=conversation_id,
            session_id=session_id,
            status=status,
            query=query,
            limit=limit,
        )
    )
    return TaskListResponse(items=[TaskResponse(**asdict(task)) for task in result.items])


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    response_model_exclude_none=True,
    responses={404: {"model": ErrorResponse}},
    summary="查询任务",
)
async def get_task(
    task_id: str,
    service: TaskServiceDep,
) -> TaskResponse:
    result = await service.get_task(task_id)
    return TaskResponse(**asdict(result))


@router.post(
    "/{task_id}/complete",
    response_model=TaskResponse,
    response_model_exclude_none=True,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="完成任务",
)
async def complete_task(
    task_id: str,
    service: TaskServiceDep,
) -> TaskResponse:
    result = await service.complete_task(CompleteTaskCommand(task_id=task_id))
    return TaskResponse(**asdict(result))


@router.post(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    response_model_exclude_none=True,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="取消任务",
)
async def cancel_task(
    task_id: str,
    service: TaskServiceDep,
) -> TaskResponse:
    result = await service.cancel_task(CancelTaskCommand(task_id=task_id))
    return TaskResponse(**asdict(result))
