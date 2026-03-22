class TaskApplicationError(Exception):
    """任务应用层错误基类。"""


class TaskNotFoundError(TaskApplicationError):
    """任务不存在。"""


class TaskStateConflictError(TaskApplicationError):
    """任务当前状态不允许执行该操作。"""
