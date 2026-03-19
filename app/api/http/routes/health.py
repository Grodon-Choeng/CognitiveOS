from fastapi import APIRouter

from app.api.http.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="服务健康检查")
async def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", service="CognitiveOS")
