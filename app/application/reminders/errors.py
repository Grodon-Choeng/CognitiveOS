class ReminderApplicationError(Exception):
    """提醒应用层错误基类。"""


class ReminderNotFoundError(ReminderApplicationError):
    """提醒不存在。"""


class ReminderWorkflowNotStartedError(ReminderApplicationError):
    """提醒尚未关联工作流。"""


class ReminderWorkflowStartError(ReminderApplicationError):
    """提醒工作流启动失败。"""


class ReminderWorkflowCancelError(ReminderApplicationError):
    """提醒工作流取消失败。"""


class ReminderStateConflictError(ReminderApplicationError):
    """提醒当前状态不允许执行该操作。"""
