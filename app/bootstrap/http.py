from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.http.errors.handlers import register_exception_handlers
from app.api.http.routes import api_router, health_router
from app.bootstrap.runtime import cleanup_runtime_resources
from app.config.settings import get_settings
from app.observability.logging import configure_logging
from app.observability.metrics import configure_metrics
from app.observability.tracing import configure_tracing


@asynccontextmanager
async def application_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield
    await cleanup_runtime_resources()


def create_application() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    configure_tracing(settings)
    configure_metrics(settings)
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=application_lifespan,
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app
