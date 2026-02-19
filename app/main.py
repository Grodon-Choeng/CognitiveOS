from cashews import cache
from dishka import make_async_container
from dishka.integrations.litestar import setup_dishka
from litestar import Litestar, Request
from litestar.exceptions import HTTPException
from litestar.response import Response

from app.config import settings
from app.container import AppProvider
from app.core.exceptions import AppException
from app.enums import ErrorCode
from app.middleware import APIKeyMiddleware, IMSignatureMiddleware, RequestTrackingMiddleware
from app.routes.v1 import v1_router
from app.utils.logging import logger


def exception_handler(request: Request, exc: AppException | HTTPException) -> Response:
    if isinstance(exc, AppException):
        logger.error(
            f"Application error: {exc.code.value} - {exc.message}",
            extra={"extra_fields": {"detail": exc.detail}},
        )

        status_code = _get_status_code(exc.code)
        return Response(
            content=exc.to_dict(),
            status_code=status_code,
        )

    if isinstance(exc, HTTPException):
        return Response(
            content={"error": "HTTP_ERROR", "message": exc.detail},
            status_code=exc.status_code,
        )

    logger.exception("Unexpected error")
    return Response(
        content={
            "error": ErrorCode.INTERNAL_ERROR.value,
            "message": "An unexpected error occurred",
        },
        status_code=500,
    )


def _get_status_code(code: ErrorCode) -> int:
    status_map = {
        ErrorCode.VALIDATION_ERROR: 400,
        ErrorCode.NOT_FOUND: 404,
        ErrorCode.AUTHENTICATION_ERROR: 401,
        ErrorCode.AUTHORIZATION_ERROR: 403,
        ErrorCode.RATE_LIMIT_ERROR: 429,
        ErrorCode.LLM_ERROR: 502,
        ErrorCode.EMBEDDING_ERROR: 502,
        ErrorCode.STORAGE_ERROR: 500,
        ErrorCode.INTERNAL_ERROR: 500,
    }
    return status_map.get(code, 500)


def setup_cache() -> None:
    if settings.cache_enabled:
        cache.setup(settings.cache_url)
        logger.info(f"Cache enabled: {settings.cache_url}")
    else:
        cache.setup("mem://")
        logger.info("Cache disabled, using in-memory fallback")


async def seed_prompts() -> None:
    from app.container import get_prompt_service

    service = await get_prompt_service()
    count = await service.seed_defaults()
    if count > 0:
        logger.info(f"Seeded {count} default prompts")


container = make_async_container(AppProvider())

app = Litestar(
    route_handlers=[v1_router],
    exception_handlers={
        AppException: exception_handler,
        HTTPException: exception_handler,
    },
    middleware=[
        RequestTrackingMiddleware,
        IMSignatureMiddleware,
        APIKeyMiddleware,
    ],
    debug=settings.debug,
    on_startup=[seed_prompts],
)

setup_dishka(container, app)
setup_cache()

logger.info(f"CognitiveOS started in {settings.environment.value} mode")
logger.info("API version: v1, prefix: /api/v1")
logger.info(f"Markdown debug mode: {settings.markdown_debug_mode}")
logger.info(f"IM enabled: {settings.im_enabled}, provider: {settings.im_provider.value}")
logger.info(f"LLM model: {settings.llm_model}, embedding: {settings.embedding_model}")
