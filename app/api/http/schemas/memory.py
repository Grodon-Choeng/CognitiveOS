from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

MemoryStatusFilter = Literal["active", "archived"]


class CreateMemoryRequest(BaseModel):
    content: str = Field(min_length=1, description="需要写入的记忆内容。")
    memory_type: str | None = Field(default=None, description="记忆类型。")
    conversation_id: str | None = Field(default=None, description="内部统一对话 ID。")
    session_id: str | None = Field(default=None, description="内部统一会话 ID。")
    source_channel: str | None = Field(default=None, description="来源渠道。")
    source_user_id: str | None = Field(default=None, description="来源用户标识。")
    source_chat_id: str | None = Field(default=None, description="来源会话标识。")
    source_thread_id: str | None = Field(default=None, description="来源话题标识。")
    scope_object_type: str | None = Field(default=None, description="关联对象类型。")
    scope_object_id: str | None = Field(default=None, description="关联对象 ID。")
    importance: int = Field(default=3, ge=1, le=5, description="重要度。")
    expires_at: datetime | None = Field(default=None, description="过期时间。")


class MemoryResponse(BaseModel):
    memory_id: str
    content: str
    created_at: datetime
    status: str
    memory_type: str = "note"
    conversation_id: str | None = None
    session_id: str | None = None
    scope_object_type: str | None = None
    scope_object_id: str | None = None
    importance: int = 3
    expires_at: datetime | None = None
    archived_at: datetime | None = None


class MemoryListResponse(BaseModel):
    items: list[MemoryResponse]
