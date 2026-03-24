from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ReminderStatusFilter = Literal["pending", "completed", "canceled", "failed"]


class CreateReminderRequest(BaseModel):
    text: str = Field(min_length=1, description="用户输入的提醒原文。")
    remind_at: datetime
    timezone: str = Field(default="UTC")
    conversation_id: str | None = Field(default=None, description="内部统一对话 ID。")
    session_id: str | None = Field(default=None, description="内部统一会话 ID。")
    source_channel: str | None = Field(default=None, description="来源渠道。")
    source_user_id: str | None = Field(default=None, description="来源用户标识。")
    source_chat_id: str | None = Field(default=None, description="来源会话标识。")
    source_thread_id: str | None = Field(default=None, description="来源话题标识。")
    dispatch_channel: str = Field(default="console", description="提醒消息投递渠道。")
    dispatch_recipient_id: str = Field(default="local-user", description="提醒消息接收目标。")
    dispatch_chat_id: str | None = Field(default=None, description="提醒消息投递会话标识。")
    dispatch_thread_id: str | None = Field(default=None, description="提醒消息投递话题标识。")

    @model_validator(mode="after")
    def validate_thread_fields(self) -> "CreateReminderRequest":
        if self.remind_at.tzinfo is None or self.remind_at.utcoffset() is None:
            raise ValueError("remind_at 必须包含明确的时区信息。")
        if not self.timezone.strip():
            raise ValueError("timezone 不能为空。")
        _validate_chat_thread_pair(
            chat_id=self.source_chat_id,
            thread_id=self.source_thread_id,
            chat_label="source_chat_id",
            thread_label="source_thread_id",
        )
        _validate_chat_thread_pair(
            chat_id=self.dispatch_chat_id,
            thread_id=self.dispatch_thread_id,
            chat_label="dispatch_chat_id",
            thread_label="dispatch_thread_id",
        )
        return self


class ReplyReminderRequest(BaseModel):
    reply_text: str = Field(min_length=1, description="用户对提醒的回复内容。")


class RescheduleReminderRequest(BaseModel):
    remind_at: datetime
    timezone: str = Field(default="UTC")
    text: str | None = Field(default=None, min_length=1, description="更新后的提醒内容。")

    @model_validator(mode="after")
    def validate_schedule(self) -> "RescheduleReminderRequest":
        if self.remind_at.tzinfo is None or self.remind_at.utcoffset() is None:
            raise ValueError("remind_at 必须包含明确的时区信息。")
        if not self.timezone.strip():
            raise ValueError("timezone 不能为空。")
        return self


class ReminderResponse(BaseModel):
    reminder_id: str
    text: str
    remind_at: datetime
    timezone: str
    status: str
    conversation_id: str | None = None
    session_id: str | None = None
    workflow_id: str | None = None


class ReminderListResponse(BaseModel):
    items: list[ReminderResponse]


class ReminderReplyResponse(BaseModel):
    reminder_id: str
    reply_text: str
    accepted: bool
    status: str


def _validate_chat_thread_pair(
    *,
    chat_id: str | None,
    thread_id: str | None,
    chat_label: str,
    thread_label: str,
) -> None:
    if thread_id is not None and chat_id is None:
        raise ValueError(f"{thread_label} 不能脱离 {chat_label} 单独提供。")
