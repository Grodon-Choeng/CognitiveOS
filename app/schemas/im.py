from dataclasses import dataclass, field

from app.enums import IMProvider


@dataclass
class IMTestResponse:
    success: bool = field(metadata={"description": "是否发送成功"})
    error: str | None = field(default=None, metadata={"description": "错误信息，成功时为 null"})
    provider: str | None = field(default=None, metadata={"description": "发送使用的 IM 平台"})


@dataclass
class IMNotifyResponse:
    success: bool = field(metadata={"description": "是否发送成功"})
    error: str | None = field(default=None, metadata={"description": "错误信息，成功时为 null"})
    provider: str | None = field(default=None, metadata={"description": "发送使用的 IM 平台"})


@dataclass
class IMProviderInfo:
    provider: str = field(metadata={"description": "IM 平台标识"})
    name: str = field(metadata={"description": "IM 平台名称"})
    enabled: bool = field(metadata={"description": "是否启用"})


@dataclass
class IMProvidersResponse:
    providers: list[IMProviderInfo] = field(metadata={"description": "可用的 IM 平台列表"})


@dataclass
class SetUserChannelRequest:
    provider: IMProvider = field(metadata={"description": "IM 平台标识"})


@dataclass
class SetUserChannelResponse:
    success: bool = field(metadata={"description": "是否设置成功"})
    provider: str = field(metadata={"description": "设置的 IM 平台"})


@dataclass
class WebhookRequest:
    content: str = field(metadata={"description": "消息内容"})
    source: str = field(default="webhook", metadata={"description": "来源标识"})
    user_id: str | None = field(
        default=None, metadata={"description": "用户标识，用于记录最后使用的 IM 渠道"}
    )


@dataclass
class WebhookResponse:
    success: bool = field(metadata={"description": "是否处理成功"})
    message: str | None = field(default=None, metadata={"description": "响应消息"})
    error: str | None = field(default=None, metadata={"description": "错误信息"})
