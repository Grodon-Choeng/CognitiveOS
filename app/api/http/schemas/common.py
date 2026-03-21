from pydantic import BaseModel

from app.infrastructure.types import JSONObject


class HealthResponse(BaseModel):
    status: str
    service: str


class ErrorResponse(BaseModel):
    detail: str


class AuditEventResponse(BaseModel):
    kind: str
    event_id: str
    recorded_at: str
    conversation_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    chain_id: str | None = None
    request_id: str | None = None
    success: bool
    summary: str
    payload: JSONObject
