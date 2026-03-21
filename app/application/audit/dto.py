from dataclasses import dataclass, field

from app.infrastructure.types import JSONObject


@dataclass(slots=True, frozen=True)
class AuditCursorDTO:
    recorded_at: str
    event_id: str


@dataclass(slots=True, frozen=True)
class AuditEventDTO:
    kind: str
    event_id: str
    recorded_at: str
    conversation_id: str | None
    session_id: str | None
    trace_id: str | None
    chain_id: str | None
    request_id: str | None
    success: bool
    summary: str
    payload: JSONObject = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class AuditEventPageDTO:
    items: list[AuditEventDTO]
    next_cursor: str | None = None
