from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request

from app.api.http.errors.handlers import register_exception_handlers
from app.api.http.routes import api_router, health_router
from app.bootstrap.container import create_http_container
from app.bootstrap.runtime import cleanup_runtime_resources
from app.config.settings import Settings, get_settings
from app.observability.context import bind_observability_context, reset_observability_context
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

    @app.middleware("http")
    async def attach_observability_context(request: Request, call_next: object) -> object:
        next_handler = call_next
        trace_id = request.headers.get("x-trace-id") or str(uuid4())
        chain_id = request.headers.get("x-chain-id") or trace_id
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.trace_id = trace_id
        request.state.chain_id = chain_id
        request.state.request_id = request_id
        token = bind_observability_context(
            trace_id=trace_id,
            chain_id=chain_id,
            request_id=request_id,
            process_role="api",
        )
        try:
            response = await next_handler(request)
            response.headers["X-Trace-Id"] = trace_id
            response.headers["X-Chain-Id"] = chain_id
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            reset_observability_context(token)

    setup_dishka(container=container, app=app)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router, prefix=active_settings.api_prefix)
    return app
