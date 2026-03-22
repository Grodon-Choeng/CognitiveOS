class MemoryApplicationError(Exception):
    """记忆应用层错误基类。"""


class MemoryNotFoundError(MemoryApplicationError):
    """记忆不存在。"""
