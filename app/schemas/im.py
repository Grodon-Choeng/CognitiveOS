from dataclasses import dataclass, field


@dataclass
class IMTestResponse:
    success: bool = field(metadata={"description": "是否发送成功"})
    error: str | None = field(default=None, metadata={"description": "错误信息，成功时为 null"})


@dataclass
class IMNotifyResponse:
    success: bool = field(metadata={"description": "是否发送成功"})
    error: str | None = field(default=None, metadata={"description": "错误信息，成功时为 null"})
