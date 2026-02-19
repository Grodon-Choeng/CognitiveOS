from typing import Any

from app.services.vector_store import VectorStore
from app.tasks.worker import get_redis_settings


async def index_knowledge_item(ctx: dict, item_id: int) -> dict[str, Any]:
    from app.container import get_embedding_service, get_knowledge_item_service

    knowledge_service = await get_knowledge_item_service()
    embedding_service = await get_embedding_service()
    vector_store = VectorStore()

    item = await knowledge_service.get_by_id(item_id)
    if not item:
        return {"success": False, "error": f"Item {item_id} not found"}

    if not item.raw_text:
        return {"success": False, "error": f"Item {item_id} has no content"}

    embedding = await embedding_service.generate_and_store(item)
    vector_store.add(item, embedding)

    return {"success": True, "item_id": item_id}


async def rebuild_all_indexes(ctx: dict) -> dict[str, Any]:
    from app.container import get_embedding_service, get_knowledge_item_service

    knowledge_service = await get_knowledge_item_service()
    embedding_service = await get_embedding_service()
    vector_store = VectorStore()

    items = await knowledge_service.filter_without_embedding(limit=1000)

    if not items:
        return {"success": True, "indexed_count": 0}

    embeddings = await embedding_service.batch_generate_and_store(items)
    vector_store.add_batch(items, embeddings)

    return {"success": True, "indexed_count": len(items)}


async def startup(ctx: dict) -> None:
    pass


async def shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    functions = [index_knowledge_item, rebuild_all_indexes]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = get_redis_settings()
