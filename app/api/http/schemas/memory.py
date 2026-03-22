from datetime import datetime

from pydantic import BaseModel, Field


class CreateMemoryRequest(BaseModel):
    content: str = Field(min_length=1, description="需要写入的记忆内容。")
    conversation_id: str | None = Field(default=None, description="内部统一对话 ID。")
    session_id: str | None = Field(default=None, description="内部统一会话 ID。")
    source_channel: str | None = Field(default=None, description="来源渠道。")
    source_user_id: str | None = Field(default=None, description="来源用户标识。")
    source_chat_id: str | None = Field(default=None, description="来源会话标识。")
    source_thread_id: str | None = Field(default=None, description="来源话题标识。")


class MemoryResponse(BaseModel):
    memory_id: str
    content: str
    created_at: datetime
    conversation_id: str | None = None
    session_id: str | None = None


class MemoryListResponse(BaseModel):
    items: list[MemoryResponse]
