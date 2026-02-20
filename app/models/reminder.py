from piccolo.columns import Boolean, Integer, Text, Timestamp, Varchar

from app.core import BaseModel


class Reminder(BaseModel):
    content = Text(help_text="提醒内容")
    remind_at = Timestamp(help_text="提醒时间")
    user_id = Varchar(length=100, help_text="用户标识")
    channel_id = Integer(null=True, help_text="Discord 频道 ID")
    guild_id = Integer(null=True, help_text="Discord 服务器 ID")
    is_sent = Boolean(default=False, help_text="是否已发送")
    is_advance_sent = Boolean(default=False, help_text="是否已发送提前提醒")
    sent_at = Timestamp(null=True, default=None, help_text="实际发送时间")
    provider = Varchar(length=20, default="discord", help_text="IM 平台")

    class Meta:
        tablename = "reminder"
