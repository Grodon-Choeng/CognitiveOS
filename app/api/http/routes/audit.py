from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.http.deps.services import get_audit_service
from app.api.http.schemas.common import AuditEventResponse
from app.application.audit.service import AuditQueryService

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", summary="查询统一审计事件")
async def list_audit_events(
    service: Annotated[AuditQueryService, Depends(get_audit_service)],
    kind: str = Query(..., description="事件类型：message/model/tool/workflow"),
    conversation_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[AuditEventResponse]:
    records = await service.list_events(
        kind=kind,
        conversation_id=conversation_id,
        session_id=session_id,
        limit=limit,
    )
    return [AuditEventResponse(**asdict(record)) for record in records]
