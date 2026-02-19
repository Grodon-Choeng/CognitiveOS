from dataclasses import dataclass

from litestar import get

from app.utils.times import utc_time


@dataclass
class HealthResponse:
    status: str
    timestamp: str
    version: str = "0.1.0"


@get("/health", sync_to_thread=False)
def health() -> HealthResponse:
    return HealthResponse(status="healthy", timestamp=utc_time().isoformat())
