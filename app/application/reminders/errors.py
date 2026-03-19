class ReminderApplicationError(Exception):
    """提醒应用层错误基类。"""


class ReminderNotFoundError(ReminderApplicationError):
    """提醒不存在。"""


class ReminderWorkflowNotStartedError(ReminderApplicationError):
    """提醒尚未关联工作流。"""
