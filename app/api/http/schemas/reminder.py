from datetime import datetime

from pydantic import BaseModel, Field


class CreateReminderRequest(BaseModel):
    text: str = Field(min_length=1, description="用户输入的提醒原文。")
    remind_at: datetime
    timezone: str = Field(default="UTC")
    dispatch_channel: str = Field(default="console", description="提醒消息投递渠道。")
    dispatch_recipient_id: str = Field(default="local-user", description="提醒消息接收目标。")


class ReplyReminderRequest(BaseModel):
    reply_text: str = Field(min_length=1, description="用户对提醒的回复内容。")


class ReminderResponse(BaseModel):
    reminder_id: str
    text: str
    remind_at: datetime
    timezone: str
    status: str
    workflow_id: str | None = None


class ReminderReplyResponse(BaseModel):
    reminder_id: str
    reply_text: str
    accepted: bool
    status: str
