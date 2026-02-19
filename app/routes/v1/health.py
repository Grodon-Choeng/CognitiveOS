from dataclasses import dataclass

from litestar import get

from app.constants import API_VERSION
from app.utils.times import utc_time


@dataclass
class HealthResponse:
    status: str
    timestamp: str
    version: str = "0.1.0"
    api_version: str = API_VERSION


@get(
    "/health",
    sync_to_thread=False,
    summary="健康检查",
    description="检查服务运行状态，返回服务健康信息",
    tags=["系统"],
)
def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        timestamp=utc_time().isoformat(),
    )
