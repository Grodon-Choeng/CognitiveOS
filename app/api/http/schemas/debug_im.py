from pydantic import BaseModel, Field, model_validator

from app.infrastructure.types import JSONObject


class DebugIMSendMessageRequest(BaseModel):
    user_identity: str = Field(min_length=1, description="调试 IM 用户标识。")
    text: str = Field(min_length=1, description="发送的文本内容。")
    chat_id: str | None = Field(default=None, description="调试会话 ID。")
    thread_id: str | None = Field(default=None, description="调试话题 ID。")
    reply_to_message_id: str | None = Field(default=None, description="引用回复的消息 ID。")
    raw_payload: JSONObject = Field(
        default_factory=dict,
        description="原始调试载荷；不提供时会自动构造。",
    )

    @model_validator(mode="after")
    def validate_thread_fields(self) -> "DebugIMSendMessageRequest":
        if self.thread_id is not None and self.chat_id is None:
            raise ValueError("thread_id 不能脱离 chat_id 单独提供。")
        return self


class DebugIMSendMessageResponse(BaseModel):
    accepted: bool
    conversation_id: str
    session_id: str
    message_id: str
    handled: bool
    handled_by: str | None = None
    reason: str | None = None
    response_text: str | None = None


class DebugIMMessageResponse(BaseModel):
    event_id: str
    recorded_at: str
    direction: str
    channel: str
    user_identity: str | None = None
    chat_id: str | None = None
    thread_id: str | None = None
    conversation_id: str | None = None
    session_id: str | None = None
    external_message_id: str | None = None
    root_message_id: str | None = None
    parent_message_id: str | None = None
    text: str | None = None
    success: bool
    adapter_name: str | None = None
    metadata: JSONObject = Field(default_factory=dict)


class DebugIMMessageListResponse(BaseModel):
    items: list[DebugIMMessageResponse]


class DebugIMSessionResponse(BaseModel):
    session_key: str
    user_identity: str
    chat_id: str | None = None
    thread_id: str | None = None
    conversation_id: str | None = None
    session_id: str | None = None
    last_message_at: str
    last_message_direction: str
    last_message_text: str | None = None
    last_external_message_id: str | None = None


class DebugIMSessionListResponse(BaseModel):
    items: list[DebugIMSessionResponse]
