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
    is_recurring = Boolean(default=False, help_text="是否周期提醒")
    recurrence_rule = Varchar(length=64, null=True, default=None, help_text="周期规则")
    last_triggered_at = Timestamp(null=True, default=None, help_text="最近一次触发时间")
    plan_type = Varchar(length=32, default="one_time", help_text="计划类型")
    calendar_type = Varchar(length=32, default="gregorian", help_text="日历类型")
    timezone = Varchar(length=64, default="Asia/Shanghai", help_text="时区")
    advance_minutes = Integer(default=1, help_text="提前提醒分钟数，0表示关闭")
    retry_interval_minutes = Integer(default=0, help_text="重试间隔分钟数，0表示不重试")
    max_retries = Integer(default=0, help_text="最大重试次数")
    retry_count = Integer(default=0, help_text="已重试次数")
    require_ack = Boolean(default=False, help_text="是否需要确认")
    acknowledged_at = Timestamp(null=True, default=None, help_text="确认时间")
    pause_until = Timestamp(null=True, default=None, help_text="暂停到该时间")
    skip_dates = Text(null=True, default=None, help_text="跳过日期 JSON 数组")
    status = Varchar(length=16, default="active", help_text="active/paused/cancelled")

    class Meta:
        tablename = "reminder"
