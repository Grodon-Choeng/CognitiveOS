from litestar import Litestar, Request
from litestar.exceptions import HTTPException
from litestar.response import Response

from cashews import cache
from dishka import make_async_container
from dishka.integrations.litestar import setup_dishka

from app.config import settings
from app.container import AppProvider
from app.core.exceptions import AppException
from app.routes.health import health
from app.routes.im import test_im, notify_item
from app.routes.items import get_item, list_items, structure_item
from app.routes.prompts import (
    list_prompts,
    get_prompt,
    create_prompt,
    update_prompt,
    delete_prompt,
)
from app.routes.retrieval import search, rag_query, index_item, rebuild_index
from app.routes.webhook import webhook
from app.utils.logging import logger


def exception_handler(request: Request, exc: AppException | HTTPException) -> Response:
    if isinstance(exc, AppException):
        logger.error(f"Application error: {exc.code.value} - {exc.message}")
        status_code = (
            400 if exc.code.value in ["VALIDATION_ERROR", "NOT_FOUND"] else 500
        )
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
        content={"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
        status_code=500,
    )


def setup_cache() -> None:
    if settings.cache_enabled:
        cache.setup(settings.cache_url)
        logger.info(f"Cache enabled: {settings.cache_url}")
    else:
        cache.setup("mem://")
        logger.info("Cache disabled, using in-memory fallback")


async def seed_prompts() -> None:
    from app.repositories.prompt_repo import PromptRepository
    from app.services.prompt_service import PromptService

    repo = PromptRepository()
    service = PromptService(repo)
    count = await service.seed_defaults()
    if count > 0:
        logger.info(f"Seeded {count} default prompts")


container = make_async_container(AppProvider())

app = Litestar(
    route_handlers=[
        health,
        webhook,
        get_item,
        list_items,
        structure_item,
        test_im,
        notify_item,
        search,
        rag_query,
        index_item,
        rebuild_index,
        list_prompts,
        get_prompt,
        create_prompt,
        update_prompt,
        delete_prompt,
    ],
    exception_handlers={
        AppException: exception_handler,
        HTTPException: exception_handler,
    },
    debug=settings.debug,
    on_startup=[seed_prompts],
)

setup_dishka(container, app)
setup_cache()

logger.info(f"CognitiveOS started in {settings.environment.value} mode")
logger.info(f"Markdown debug mode: {settings.markdown_debug_mode}")
logger.info(
    f"IM enabled: {settings.im_enabled}, provider: {settings.im_provider.value}"
)
logger.info(f"LLM model: {settings.llm_model}, embedding: {settings.embedding_model}")
