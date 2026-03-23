from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI

from app.api.http.errors.handlers import register_exception_handlers
from app.api.http.routes import api_router, health_router
from app.bootstrap.container import create_http_container
from app.bootstrap.runtime import cleanup_runtime_resources
from app.config.settings import Settings, get_settings
from app.observability.logging import configure_logging
from app.observability.metrics import configure_metrics
from app.observability.tracing import configure_tracing


def create_application(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    configure_logging(active_settings)
    configure_tracing(active_settings)
    configure_metrics(active_settings)
    container = create_http_container(active_settings)

    @asynccontextmanager
    async def application_lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await cleanup_runtime_resources(container)

    app = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        debug=active_settings.debug,
        lifespan=application_lifespan,
    )
    setup_dishka(container=container, app=app)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=active_settings.api_prefix)
    return app
