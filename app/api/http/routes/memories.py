from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.http.deps.services import get_memory_service
from app.api.http.schemas.common import ErrorResponse
from app.api.http.schemas.memory import (
    CreateMemoryRequest,
    MemoryListResponse,
    MemoryResponse,
    MemoryStatusFilter,
)
from app.application.memory.commands import ArchiveMemoryCommand, CreateMemoryCommand
from app.application.memory.queries import ListMemoriesQuery
from app.application.memory.service import MemoryApplicationService

router = APIRouter(prefix="/memories", tags=["memories"])


@router.post(
    "",
    response_model=MemoryResponse,
    responses={404: {"model": ErrorResponse}},
    summary="写入记忆",
)
async def create_memory(
    payload: CreateMemoryRequest,
    service: Annotated[MemoryApplicationService, Depends(get_memory_service)],
) -> MemoryResponse:
    result = await service.create_memory(
        CreateMemoryCommand(
            content=payload.content,
            conversation_id=payload.conversation_id,
            session_id=payload.session_id,
            source_channel=payload.source_channel,
            source_user_id=payload.source_user_id,
            source_chat_id=payload.source_chat_id,
            source_thread_id=payload.source_thread_id,
        )
    )
    return MemoryResponse(**asdict(result))


@router.get(
    "",
    response_model=MemoryListResponse,
    summary="查询记忆列表",
)
async def list_memories(
    service: Annotated[MemoryApplicationService, Depends(get_memory_service)],
    conversation_id: str | None = None,
    session_id: str | None = None,
    status: MemoryStatusFilter | None = None,
    query: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MemoryListResponse:
    result = await service.list_memories(
        ListMemoriesQuery(
            conversation_id=conversation_id,
            session_id=session_id,
            status=status,
            query=query,
            limit=limit,
        )
    )
    return MemoryListResponse(items=[MemoryResponse(**asdict(memory)) for memory in result.items])


@router.get(
    "/{memory_id}",
    response_model=MemoryResponse,
    responses={404: {"model": ErrorResponse}},
    summary="查询记忆",
)
async def get_memory(
    memory_id: str,
    service: Annotated[MemoryApplicationService, Depends(get_memory_service)],
) -> MemoryResponse:
    result = await service.get_memory(memory_id)
    return MemoryResponse(**asdict(result))


@router.post(
    "/{memory_id}/archive",
    response_model=MemoryResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="归档记忆",
)
async def archive_memory(
    memory_id: str,
    service: Annotated[MemoryApplicationService, Depends(get_memory_service)],
) -> MemoryResponse:
    result = await service.archive_memory(ArchiveMemoryCommand(memory_id=memory_id))
    return MemoryResponse(**asdict(result))
