from dataclasses import dataclass
from typing import Any

from litestar import Controller, get

from app.constants import API_VERSION
from app.services import get_feishu_bot_status
from app.utils.times import utc_time


@dataclass
class HealthResponse:
    status: str
    timestamp: str
    version: str = "0.1.0"
    api_version: str = API_VERSION
    dependencies: dict[str, Any] | None = None


class HealthController(Controller):
    path = "/health"
    tags = ["系统"]

    @get(summary="健康检查", description="检查服务运行状态，返回服务健康信息")
    async def health(self) -> HealthResponse:
        feishu = get_feishu_bot_status()
        return HealthResponse(
            status="healthy",
            timestamp=utc_time().isoformat(),
            dependencies={
                "feishu_bot": {
                    "enabled": feishu.enabled,
                    "running": feishu.running,
                    "connected": feishu.connected,
                    "reconnect_attempts": feishu.reconnect_attempts,
                    "last_connected_at": feishu.last_connected_at,
                    "last_event_at": feishu.last_event_at,
                    "last_error_at": feishu.last_error_at,
                    "last_error": feishu.last_error,
                }
            },
        )
