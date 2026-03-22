from pydantic import BaseModel

from app.api.http.schemas.common import AuditEventResponse
from app.api.http.schemas.memory import MemoryResponse
from app.api.http.schemas.reminder import ReminderResponse
from app.api.http.schemas.task import TaskResponse


class OverviewResponse(BaseModel):
    conversation_id: str | None = None
    session_id: str | None = None
    pending_reminders: list[ReminderResponse]
    pending_tasks: list[TaskResponse]
    active_memories: list[MemoryResponse]
    recent_activity: list[AuditEventResponse]
