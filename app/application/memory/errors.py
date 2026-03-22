class MemoryApplicationError(Exception):
    """记忆应用层错误基类。"""


class MemoryNotFoundError(MemoryApplicationError):
    """记忆不存在。"""


class MemoryStateConflictError(MemoryApplicationError):
    """记忆当前状态不允许执行该操作。"""
