from litestar import Router

from app.routes.v1 import health, im, items, prompts, retrieval, webhook

v1_router = Router(
    path="/api/v1",
    route_handlers=[
        health.health,
        webhook.webhook,
        items.list_items,
        items.get_item,
        items.structure_item,
        im.test_im,
        im.notify_item,
        retrieval.search,
        retrieval.rag_query,
        retrieval.index_item,
        retrieval.rebuild_index,
        prompts.list_prompts,
        prompts.get_prompt,
        prompts.create_prompt,
        prompts.update_prompt,
        prompts.delete_prompt,
    ],
)
