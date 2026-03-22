from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

TaskStatusFilter = Literal["pending", "completed", "canceled"]


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1, description="任务标题。")
    conversation_id: str | None = Field(default=None, description="内部统一对话 ID。")
    session_id: str | None = Field(default=None, description="内部统一会话 ID。")
    source_channel: str | None = Field(default=None, description="来源渠道。")
    source_user_id: str | None = Field(default=None, description="来源用户标识。")
    source_chat_id: str | None = Field(default=None, description="来源会话标识。")
    source_thread_id: str | None = Field(default=None, description="来源话题标识。")


class TaskResponse(BaseModel):
    task_id: str
    title: str
    created_at: datetime
    status: str
    conversation_id: str | None = None
    session_id: str | None = None
    completed_at: datetime | None = None


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
