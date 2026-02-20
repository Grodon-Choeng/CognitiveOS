from dataclasses import dataclass

from litestar import Controller, get

from app.constants import API_VERSION
from app.utils.times import utc_time


@dataclass
class HealthResponse:
    status: str
    timestamp: str
    version: str = "0.1.0"
    api_version: str = API_VERSION


class HealthController(Controller):
    path = "/health"
    tags = ["系统"]

    @get(summary="健康检查", description="检查服务运行状态，返回服务健康信息")
    async def health(self) -> HealthResponse:
        return HealthResponse(
            status="healthy",
            timestamp=utc_time().isoformat(),
        )
