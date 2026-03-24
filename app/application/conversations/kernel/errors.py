class AssistantPlanningError(RuntimeError):
    """规划阶段失败。"""


class AssistantResolutionError(RuntimeError):
    """对象解析阶段失败。"""


class AssistantExecutionError(RuntimeError):
    """执行阶段失败。"""
