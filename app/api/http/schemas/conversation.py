from pydantic import BaseModel, Field, model_validator

from app.infrastructure.types import JSONObject


class ConversationMessageRequest(BaseModel):
    channel: str = Field(min_length=1, description="消息来源渠道。")
    message_type: str = Field(min_length=1, description="消息类型。")
    user_identity: str = Field(min_length=1, description="发送者在来源渠道中的身份标识。")
    external_message_id: str | None = Field(default=None, description="渠道侧消息 ID。")
    root_message_id: str | None = Field(default=None, description="根消息 ID。")
    parent_message_id: str | None = Field(default=None, description="父消息 ID。")
    chat_id: str | None = Field(default=None, description="来源会话 ID。")
    thread_id: str | None = Field(default=None, description="来源话题 ID。")
    text: str | None = Field(default=None, description="文本内容。")
    raw_payload: JSONObject = Field(
        default_factory=dict,
        description="原始入站载荷；如果未提供，将由当前请求体自动构造。",
    )

    @model_validator(mode="after")
    def validate_thread_fields(self) -> "ConversationMessageRequest":
        if self.thread_id is not None and self.chat_id is None:
            raise ValueError("thread_id 不能脱离 chat_id 单独提供。")
        if self.message_type == "text" and (self.text is None or not self.text.strip()):
            raise ValueError("text 类型消息必须提供 text 内容。")
        return self


class ConversationMessageResponse(BaseModel):
    handled: bool
    conversation_id: str
    session_id: str
    handled_by: str | None = None
    reason: str | None = None
