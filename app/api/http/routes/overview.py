from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.http.deps.services import get_overview_service
from app.api.http.schemas.memory import MemoryResponse
from app.api.http.schemas.overview import OverviewResponse
from app.api.http.schemas.reminder import ReminderResponse
from app.api.http.schemas.task import TaskResponse
from app.application.overview.queries import GetOverviewQuery
from app.application.overview.service import OverviewApplicationService

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get(
    "",
    response_model=OverviewResponse,
    summary="查询统一产品概览",
)
async def get_overview(
    service: Annotated[OverviewApplicationService, Depends(get_overview_service)],
    conversation_id: str | None = None,
    session_id: str | None = None,
    reminder_limit: Annotated[int, Query(ge=1, le=20)] = 5,
    task_limit: Annotated[int, Query(ge=1, le=20)] = 5,
    memory_limit: Annotated[int, Query(ge=1, le=20)] = 5,
) -> OverviewResponse:
    result = await service.get_overview(
        GetOverviewQuery(
            conversation_id=conversation_id,
            session_id=session_id,
            reminder_limit=reminder_limit,
            task_limit=task_limit,
            memory_limit=memory_limit,
        )
    )
    return OverviewResponse(
        conversation_id=result.conversation_id,
        session_id=result.session_id,
        pending_reminders=[
            ReminderResponse(**asdict(reminder)) for reminder in result.pending_reminders
        ],
        pending_tasks=[TaskResponse(**asdict(task)) for task in result.pending_tasks],
        active_memories=[MemoryResponse(**asdict(memory)) for memory in result.active_memories],
    )
