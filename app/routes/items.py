from uuid import UUID

from litestar import post, get
from dishka import FromDishka
from dishka.integrations.litestar import inject

from app.schemas.webhook import (
    KnowledgeItemResponse,
    KnowledgeItemListResponse,
    StructuredResponse,
)
from app.services.knowledge_item_service import KnowledgeItemService
from app.services.structuring_service import StructuringService
from app.utils.jsons import parse_json_field


@post("/items/{item_uuid:uuid}/structure")
@inject
async def structure_item(
    item_uuid: UUID,
    knowledge_service: FromDishka[KnowledgeItemService],
    structuring_service: FromDishka[StructuringService],
) -> StructuredResponse:
    item = await knowledge_service.get_by_uuid(item_uuid)
    output = await structuring_service.generate_markdown(item)

    return StructuredResponse(
        uuid=item.uuid,
        title=output.title,
        file_path=str(output.file_path) if output.file_path else None,
    )


@get("/items/{item_uuid:uuid}")
@inject
async def get_item(
    item_uuid: UUID,
    knowledge_service: FromDishka[KnowledgeItemService],
) -> KnowledgeItemResponse:
    item = await knowledge_service.get_by_uuid(item_uuid)

    return KnowledgeItemResponse(
        uuid=item.uuid,
        raw_text=item.raw_text,
        structured_text=item.structured_text,
        source=item.source,
        tags=parse_json_field(item.tags),
        links=parse_json_field(item.links),
        created_at=item.created_at.isoformat() if item.created_at else "",
        updated_at=item.updated_at.isoformat() if item.updated_at else "",
    )


@get("/items")
@inject
async def list_items(
    knowledge_service: FromDishka[KnowledgeItemService],
    limit: int = 10,
) -> list[KnowledgeItemListResponse]:
    items = await knowledge_service.get_recent(limit=limit)
    return [
        KnowledgeItemListResponse(
            uuid=item.uuid,
            raw_text=item.raw_text[:100] + "..."
            if len(item.raw_text) > 100
            else item.raw_text,
            source=item.source,
            tags=parse_json_field(item.tags),
            created_at=item.created_at.isoformat() if item.created_at else "",
        )
        for item in items
    ]
