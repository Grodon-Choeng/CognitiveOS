from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.http.deps.services import get_audit_service
from app.api.http.schemas.common import AuditEventPageResponse, AuditEventResponse
from app.application.audit.service import AuditQueryService

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", summary="查询统一审计事件")
async def list_audit_events(
    service: Annotated[AuditQueryService, Depends(get_audit_service)],
    kind: Annotated[str, Query(description="事件类型：message/model/tool/workflow")],
    conversation_id: Annotated[str | None, Query()] = None,
    session_id: Annotated[str | None, Query()] = None,
    success: Annotated[bool | None, Query()] = None,
    channel: Annotated[str | None, Query()] = None,
    provider: Annotated[str | None, Query()] = None,
    tool_name: Annotated[str | None, Query()] = None,
    workflow_type: Annotated[str | None, Query()] = None,
    recorded_after: Annotated[datetime | None, Query()] = None,
    recorded_before: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditEventPageResponse:
    page = await service.list_events(
        kind=kind,
        conversation_id=conversation_id,
        session_id=session_id,
        success=success,
        channel=channel,
        provider=provider,
        tool_name=tool_name,
        workflow_type=workflow_type,
        recorded_after=recorded_after,
        recorded_before=recorded_before,
        cursor=cursor,
        limit=limit,
    )
    return AuditEventPageResponse(
        items=[AuditEventResponse(**asdict(record)) for record in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/timeline", summary="查询统一审计时间线")
async def list_audit_timeline(
    service: Annotated[AuditQueryService, Depends(get_audit_service)],
    conversation_id: Annotated[str | None, Query()] = None,
    session_id: Annotated[str | None, Query()] = None,
    success: Annotated[bool | None, Query()] = None,
    channel: Annotated[str | None, Query()] = None,
    provider: Annotated[str | None, Query()] = None,
    tool_name: Annotated[str | None, Query()] = None,
    workflow_type: Annotated[str | None, Query()] = None,
    recorded_after: Annotated[datetime | None, Query()] = None,
    recorded_before: Annotated[datetime | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditEventPageResponse:
    page = await service.list_timeline(
        conversation_id=conversation_id,
        session_id=session_id,
        success=success,
        channel=channel,
        provider=provider,
        tool_name=tool_name,
        workflow_type=workflow_type,
        recorded_after=recorded_after,
        recorded_before=recorded_before,
        cursor=cursor,
        limit=limit,
    )
    return AuditEventPageResponse(
        items=[AuditEventResponse(**asdict(record)) for record in page.items],
        next_cursor=page.next_cursor,
    )
