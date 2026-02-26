from dataclasses import dataclass
from typing import Any

from litestar import Controller, get

from app.channels.registry import CHANNEL_STATUS_GETTERS
from app.constants import API_VERSION
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
        dependencies: dict[str, Any] = {}
        health_flags: list[bool] = []

        for provider, getter in CHANNEL_STATUS_GETTERS.items():
            status = getter()
            healthy = not status.enabled or (status.running and status.connected)
            health_flags.append(healthy)

            payload = {
                "enabled": status.enabled,
                "running": status.running,
                "connected": status.connected,
                "reconnect_attempts": status.reconnect_attempts,
                "last_connected_at": status.last_connected_at,
                "last_event_at": status.last_event_at,
                "last_error_at": status.last_error_at,
                "last_error": status.last_error,
            }
            guild_count = getattr(status, "guild_count", None)
            if guild_count is not None:
                payload["guild_count"] = guild_count

            dependencies[f"{provider}_bot"] = payload

        if not health_flags or all(health_flags):
            status = "healthy"
        elif any(health_flags):
            status = "degraded"
        else:
            status = "unhealthy"

        return HealthResponse(
            status=status,
            timestamp=utc_time().isoformat(),
            dependencies=dependencies,
        )
