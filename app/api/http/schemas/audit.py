from enum import StrEnum


class AuditEventKind(StrEnum):
    MESSAGE = "message"
    MODEL = "model"
    TOOL = "tool"
    WORKFLOW = "workflow"
