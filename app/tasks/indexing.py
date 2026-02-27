from typing import Any

from dishka import make_async_container

from app.container import AppProvider
from app.services import EmbeddingService, KnowledgeItemService, VectorStore

from .worker import get_redis_settings

_container = make_async_container(AppProvider())


async def startup(ctx: dict) -> None:
    ctx["container"] = _container


async def shutdown(ctx: dict) -> None:
    container = ctx.pop("container", None)
    if container is not None and hasattr(container, "close"):
        await container.close()


def _get_container(ctx: dict):
    return ctx.get("container", _container)


async def index_knowledge_item(ctx: dict, item_id: int) -> dict[str, Any]:
    container = _get_container(ctx)
    async with container() as request_container:
        knowledge_service = await request_container.get(KnowledgeItemService)
        embedding_service = await request_container.get(EmbeddingService)
        vector_store = await request_container.get(VectorStore)

        item = await knowledge_service.get_by_id(item_id)
        if not item:
            return {"success": False, "error": f"Item {item_id} not found"}

        if not item.raw_text:
            return {"success": False, "error": f"Item {item_id} has no content"}

        embedding = await embedding_service.generate_and_store(item)
        vector_store.add(item, embedding)

        return {"success": True, "item_id": item_id}


async def rebuild_all_indexes(ctx: dict) -> dict[str, Any]:
    container = _get_container(ctx)
    async with container() as request_container:
        knowledge_service = await request_container.get(KnowledgeItemService)
        embedding_service = await request_container.get(EmbeddingService)
        vector_store = await request_container.get(VectorStore)

        items = await knowledge_service.filter_without_embedding(limit=1000)

        if not items:
            return {"success": True, "indexed_count": 0}

        embeddings = await embedding_service.batch_generate_and_store(items)
        vector_store.add_batch(items, embeddings)

        return {"success": True, "indexed_count": len(items)}


class WorkerSettings:
    functions = [index_knowledge_item, rebuild_all_indexes]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()
